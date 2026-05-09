import os
from datetime import datetime

class NameGenerator:
    def __init__(self, output_directory, fileName):
       self.out_directory = output_directory
       self.fileName = os.path.join(self.getDirectory(), f"{fileName}_{datetime.today().strftime("%Y-%m-%d")}.txt")

    def ProcessName(self):
        current_date = datetime.today().strftime("%Y-%m-%d")
        self.fileName = os.path.join(self.getDirectory(), f"{self.getName()}_{current_date}.txt")

    def getName(self):
        return self.fileName
    
    def setName(self, name):
        self.fileName = name

    def getDirectory(self):
        return self.out_directory
    
    def setDirectory(self,location):
        self.out_directory = location

