import sys
sys.path.append("/home/pi/mycroft-core/.venv/lib/python3.7/site-packages")
from mycroft_bus_client import MessageBusClient, Message

import pigpio
import subprocess #for rebooting
#import action_light
from operator_peripherals import ActionLight, Bell, ComboEncoder
#import os
import time
pins = pigpio.pi()

pins.set_mode(4, pigpio.INPUT)
crank = ComboEncoder(17, 18, 20)
light = ActionLight(27)
bell = Bell(22)
pins.set_mode(24, pigpio.INPUT)
pins.set_mode(26, pigpio.INPUT)

print('Setting up client to connect to a local mycroft instance')
client = MessageBusClient()
print('Connected to messagebus!')

#Hook Control
def unhook(gpio, level, tick):
    client.emit(Message('mycroft.mic.listen'))
    light.pulse(0.1, 30, None, 1) #Flicker on
    light.pulse(0.05, 25, None, 1)
    light.pulse(0.1, 100, None, 1)
    light.pulse(0.15, 80, None, 1)


#Listening Controls
def wakeword(message):
    #pins.write(27,1) #simple
    light.pulse(0.1, 30, None, 1) #Flicker on
    light.pulse(0.05, 25, None, 1)
    light.pulse(0.1, 100, None, 1)
    light.pulse(0.15, 80, None, 1)

def begin_listening(message):
    #pins.write(27,1) #simple
    light.pulse(1.1, 25, 80) #Continuous wavering

def end_listening(message):
    #pins.write(27,0) #simple
    light.pulse(0.2, 20, None, 1) #Flicker off
    light.pulse(0.05, 25, None, 1)
    light.pulse(0.2, 0, None, 1)


#Multimedia Controls
def play():
    print('play')
#    client.emit(Message('mycroft.audio.service.resume'))
    client.emit(Message('play:start',
                       {'skill_id': 'mycroft-spotify.forslund',
                        'phrase': '',
                        'callback_data': {'type': 'continue'}}))

def pause():
    print('pause')
    client.emit(Message('mycroft.audio.service.pause'))

def next_track():
    print('next')
    client.emit(Message('mycroft.audio.service.next'))

def previous_track():
    print('previous')
    client.emit(Message('mycroft.audio.service.prev'))

def change_volume(args):
    print(f'changed volume by {args[0]}')
#    client.emit(Message('recognizer_loop:utterance',
#                       {"utterances": ["play spotify"],
#                        "lang": "en-us"}))


#Bell controlls
def timer_done(message):
    print(message.data)
    light.pulse(0.5, 100, None)
    bell.ring([.9,.9,.3,.3])

def timer_stopped(message):
    print(message.data)
    light.pulse(0.2, 0, None, 1)
    bell.ring([0])


#Bell Stop
def stop(gpio, level, tick):
    print('stop')
    client.emit(Message('mycroft.stop'))


#Developer Button
def reset(gpio, level, tick):
    if(pins.read(24) == 1):
        client.emit(Message('speak', {"utterance": "Shutting Down", "lang": "en-us"}))
        light.pulse(.2, 100, 0, 10)
        time.sleep(3)
        #self.bus.emit(Message('system.shutdown')) #docs say this "force[s] a linux shutdown", but I'll believe it when I see it (it wicked doesn't do that)
        subprocess.Popen(['sudo','shutdown','-h','now'])
    else:
        client.emit(Message('speak', {"utterance": "Restarting", "lang": "en-us"}))
        light.pulse(.2, 100, 0, 6)
        time.sleep(3)
        #self.bus.emit(Message('system.restart')) #same deal here
        subprocess.Popen(['sudo','shutdown','-r','now'])

#Startup Signal
def startup_alert(message):
    light.pulse(0.5, 100, None, 4)
    bell.ring([0.6, 0.6], 4, 1)
#    client.emit(Message('recognizer_loop:utterance',
#                       {"utterances": ["play spotify"],
#                        "lang": "en-us"}))
#                        "session": session_id}))

#print utterances
def uttered(message):
    print(message.data)

light.pulse(0.5, 40, None, 1)
light.pulse(0.7, 10, 40)

cbUnhook = pins.callback(4, pigpio.RISING_EDGE, unhook)
cbStop = pins.callback(24, pigpio.RISING_EDGE, stop)
cbReset = pins.callback(26, pigpio.RISING_EDGE, reset)

crank.create_callback('play', [-10, 10], play)
crank.create_callback('pause', [10, -10], pause)
crank.create_callback('next_track', [-5, 25], next_track)
crank.create_callback('previous_track', [5, -25], previous_track)
crank.create_callback('changeVolume', [0], change_volume)

client.on('recognizer_loop:wakeword', wakeword)
client.on('recognizer_loop:record_begin', begin_listening)
client.on('recognizer_loop:record_end', end_listening)
client.on('skill.mycrofttimer.expired', timer_done)
client.on('skill.mycrofttimer.cancelled', timer_stopped)
client.on('mycroft.ready', startup_alert)
client.on('recognizer_loop:utterance', uttered)
try:
    client.run_forever()
except KeyboardInterrupt:
    #Cleaning up
    cbUnhook.cancel()
    cbStop.cancel()
    cbReset.cancel()
    pins.stop()

