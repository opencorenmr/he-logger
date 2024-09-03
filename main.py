# coding: UTF-8
'''
Helium Logger
=============
ver 3.0

Takeda (2024 Aug)
'''
from kivy.config import Config
#Config.set('graphics', 'width', '800')
#Config.set('graphics', 'height', '480')

import time
import threading
from datetime import datetime
from kivy.uix.widget import Widget
from kivy.app import App
from os.path import dirname, join
from kivy.uix.progressbar import ProgressBar
from kivy.properties import NumericProperty, StringProperty, BooleanProperty,\
    ListProperty
from kivy.properties import ObjectProperty
from kivy.clock import Clock
from kivy.animation import Animation
from kivy.uix.screenmanager import Screen, ScreenManager
from kivy.base import runTouchApp
from kivy.uix.spinner import Spinner
from kivy.graphics import Color, Ellipse, Rectangle
from kivy.core.text import Label as CoreLabel

from kivy.lang import Builder

#build window with KVLanguage file
Builder.load_file('mainWindow.kv')

#GPIO settings
import RPi.GPIO as GPIO

GPIO.setmode(GPIO.BCM)
GPIO.setup(25, GPIO.OUT)

GPIO.setmode(GPIO.BCM)
SPICLK = 11
SPIMOSI = 10
SPIMISO = 9
SPICS = 8

GPIO.setup(SPICLK, GPIO.OUT)
GPIO.setup(SPIMOSI, GPIO.OUT)
GPIO.setup(SPIMISO, GPIO.IN)
GPIO.setup(SPICS, GPIO.OUT)


#GPIO read AD converter
def readadc(adcnum, clockpin, mosipin, misopin, cspin):
    if adcnum > 7 or adcnum < 0:
        return -1
    GPIO.output(cspin, GPIO.HIGH)
    GPIO.output(clockpin, GPIO.LOW)
    GPIO.output(cspin, GPIO.LOW)

    commandout = adcnum
    commandout |= 0x18
    commandout <<= 3
    for i in range(5):
        if commandout & 0x80:
            GPIO.output(mosipin, GPIO.HIGH)
        else:
            GPIO.output(mosipin, GPIO.LOW)
        commandout <<= 1
        GPIO.output(clockpin, GPIO.HIGH)
        GPIO.output(clockpin, GPIO.LOW)
    adcout = 0

    for i in range(13):
        GPIO.output(clockpin, GPIO.HIGH)
        GPIO.output(clockpin, GPIO.LOW)
        adcout <<= 1
        if i>0 and GPIO.input(misopin)==GPIO.HIGH:
            adcout |= 0x1
    GPIO.output(cspin, GPIO.HIGH)
    return adcout


# Declare MagnetSpinner inherited from Spinner
class MagnetSpinner(Spinner):
    def __init__(self, **kwargs):
        super(MagnetSpinner, self).__init__(**kwargs)
        keys = ['select', '600', '400', '300', '300minus','200']
        self.text = keys[0]
        self.values = keys

# Declare mainLogger inherited from screens
class MainLogger(Screen):
    magnet_spinner = ObjectProperty(None)

    is_logger_active=BooleanProperty(False)
    is_clock_active=BooleanProperty(False)
    is_control_disable=BooleanProperty(True)
    nowtime=StringProperty()
    startTime=StringProperty()
    startTime_forOutput=StringProperty()
    outputfile=StringProperty()

    #-------------------------------------------------------
    sampling_interval=NumericProperty(60.0)
    #V_ref
    V_reference=NumericProperty(5.17)
    #-------------------------------------------------------

    totalflow=NumericProperty(0.0)
    totalflow_st=StringProperty('0.000 L')
    nowflow_st=StringProperty('0.000 L/min')


    #-----clock setting-----
    def on_clock(self,dt):
        self.nowtime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    def start_clock(self):
        self.is_clock_active = True
        Clock.schedule_interval(self.on_clock, 1.0)
        pass
    # do not use
    def stop_clock(self):
        self.is_clock_active = False
        Clock.unschedule(self.on_clock)
        pass
    #-----------------------


    #-----logger setting-----
    def on_logger(self,dt):
        # 12bit ADCの読み込み
        gpiovalue = readadc(0, SPICLK, SPIMOSI, SPIMISO, SPICS)

        # gpiovalue / 4096: 2^12=4096でノーマライズ。
        # その後V_referenceを掛け算。約5Vだが実際には5Vからちょっとずれている
        # こうしてADCが感知した電圧をVolt単位でV_readに保存
        V_read = self.V_reference * gpiovalue / 4096
        # このフローメータ(FCS-TM39, FUJIKIN)の出力レンジは1-5Vか。
        # だとすると、1を引いて、(5-1)=4で割り算すると、
        # フルレンジを1とした場合の現在の流量が出てきて、これをreadにストアしている？
        read = (V_read - 1) / 4
        # 推測：以下でこれをこのままL/minで出力している。ということは
        # フローメータの計測可能な最大流量がたまたま1L/minで、換算の必要がない、ということか。
        self.nowflow_st = '{:.3f} L/min'.format(read)
        file = open(self.outputfile, 'a')
        # 各行に (year-month-date hour:minute:second) - space - (flow rate) を記録する。
        file.write(self.nowtime)
        file.write(' ')
        file.write('{:.3f}\n'.format(read))
        file.close()
        #---------

        flow = read / 60 * self.sampling_interval
        #print(flow)

        self.totalflow += flow
        self.totalflow_st = '{:.3f} L'.format(self.totalflow)
        #print(self.totalflow)

    def start_logger(self, mag):

        self.is_logger_active = True

        self.startTime = datetime.now().strftime("%Y%m%d %H:%M:%S")
        self.startTime_forOutput = datetime.now().strftime("%Y%m%d_%H%M%S")

        self.totalflow = 0
        self.totalflow_st = '{:.3f} L'.format(self.totalflow)

        #file output
        self.outputfile = '/home/pi/Documents/he-flow-log-2024/{}/he-flow-log_{}.dat'.format(self.magnet_spinner.text, self.startTime_forOutput)
        file = open(self.outputfile, 'w')
        file.write('Magnet : {}\n'.format(self.magnet_spinner.text))
        file.close()

        Clock.schedule_interval(self.on_logger, self.sampling_interval)
        pass

    def stop_logger(self):
        self.is_logger_active = False
        file = open(self.outputfile, 'a')
        file.close()

        Clock.unschedule(self.on_logger)
        self.totalflow_st = '{:.3f} L'.format(self.totalflow)
        pass

    def switch_control_disable(self):
        if self.is_control_disable:
            self.is_control_disable = False
        else:
            self.is_control_disable = True

    def switch_logger(self):
        if self.is_logger_active:
            self.is_logger_active = False
            self.stop_logger()
            self.is_control_disable = True
        else:
            if self.magnet_spinner.text == 'select':
                self.is_logger_active = False
                self.is_control_disable = True
            else:
                self.is_logger_active = True
                self.start_logger(self.magnet_spinner.text)
                self.is_control_disable = True

    def endapp(self):
        GPIO.cleanup()
        exit()

#create mainLogger instance
ml = MainLogger()

class TestApp(App):

    def build(self):
        ml.start_clock()
        return ml

if __name__ == '__main__':
    TestApp().run()
    GPIO.cleanup()
