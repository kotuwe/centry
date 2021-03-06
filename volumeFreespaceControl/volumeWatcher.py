import subprocess
import psutil
import time
import logging
import requests
import json
import threading
from systemd.journal import JournaldLogHandler

log = logging.getLogger('centry')
log.addHandler(JournaldLogHandler())
log.setLevel(logging.INFO)

class WatcherThread(threading.Thread):
    def __init__(self, config):
        threading.Thread.__init__(self)
        self.configure(config)
        if config["enable"] == True:
            self._running = True
        else:
            self._running = False

    def configure(self, config):
        self.minFreeSpace = config["minFreeSpace"]
        self.increaseStep = config["increaseStep"]
        self.checkInterval = config["checkInterval"]
        self.EC2volumeId = config["EC2VolumeId"]
        self.EC2rootDrive = config["EC2rootDrive"]
        self.EC2rootPart = config["EC2rootPart"]
        self.EC2rootPartNum = config["EC2rootPartNum"]
    
    def run(self):
        while(self._running):
            freeSpace = self.getFreeSpace()
            if self.checkFreeSpaceLimit(freeSpace) == True:
                self.sendSlackNotification()
                currentVolumeSize = self.getEC2VolumeSize()
                if currentVolumeSize != 0:
                    newVolumeSize = int(currentVolumeSize) + self.increaseStep
                    if self.updateEC2VolumeSize(newVolumeSize) == True:
                        if self.updatePartitionSize() == True:
                            self.resizeFs()
            time.sleep(self.checkInterval * 60)

    def getFreeSpace(self):
        diskUsage = psutil.disk_usage('/')
        diskFreeSpace = diskUsage.free / (1024 ** 3)
        log.info('Current free space: ' + str(diskFreeSpace))
        return diskFreeSpace

    def checkFreeSpaceLimit(self, freeSpace):
        if freeSpace < self.minFreeSpace:
            log.info('Need to growup!')
            return True
        else:
            log.info('All done!')
            return False

    def getEC2VolumeSize(self):
        cmd = "aws ec2 describe-volumes --volume-ids=" + self.EC2volumeId + " | jq -r '.Volumes' | jq -r '.[].Size'"
        awsCurrentVolumeSizeRun = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        size, error = awsCurrentVolumeSizeRun.communicate()

        if error == '':
            log.info('Current volume size is: ' + str(size))
            return size
        else:
            log.info(error)
            return 0

    def updateEC2VolumeSize(self, volumeSize):
        log.info('Trying to update EC2 volume size')
        cmd = "aws ec2 modify-volume --volume-id " + self.EC2volumeId + " --size " + str(volumeSize)
        awsUpdateVolumeSizeRun = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        size, error = awsUpdateVolumeSizeRun.communicate()

        if error == '':
            log.info('Please wait 120 sec')
            time.sleep(120)
            log.info('Update EC2 volume size is complete, new volume size is: ' + getEC2VolumeSize())
            time.sleep(120)
            return True
        else:
            log.info(error)
            return False

    def updatePartitionSize(self):
        cmd = "growpart " + EC2rootDrive + " " + EC2rootPartNum
        updatePartitionSizeRun = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        size, error = updatePartitionSizeRun.communicate()

        if error == '':
            log.info('Update partition size is complete')
            return True
        else:
            log.info(error)
            return False
        
    def resizeFs(self):
        cmd = "resize2fs " + EC2rootPart
        resizeFsRun = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        size, error = resizeFsRun.communicate()

        if error == '':
            log.info('Resize FS is complete')
            return True
        else:
            log.info(error)
            return False

    def sendSlackNotification(self):
        log.info('Send Slack notification')
        payload = {'text': "Free space warning!"}
        res = requests.post(slackWebhook, json=payload)

        if res.status_code != 200:
            log.info('Notification error... code: ' + str(res.status_code) + ' with content: ' + res.content)