import queue
import threading
import pigpio
import time
from datetime import datetime, timedelta
pins = pigpio.pi()


# TEST CASES
#
#0: light.pulse(0.01,0,0,1)	stay at 0 for 0.01 seconds (times 1), then wait for a command
#1: light.pulse(1,80,20,4) 	slide back and fourth between 20 and 80%. travel between extremes in 1 second, and make 4 trips total, then wait for a command
#2: light.pulse(.7, 100, 30)	slide between 30 and 100% indefinitly. take .7 seconds to make half a cycle
#3: light.pulse(2,0,None,1)	fade to black from whatever the current brightness is over 2 seconds, then wait for a command


class ActionLight:
    def __init__(self, pin):
        pins.set_mode(pin, pigpio.OUTPUT)
        self.pin = pin

        self.range = 100
        self.frequency = 80
        pins.set_PWM_range(self.pin,  self.range)
        pins.set_PWM_frequency(self.pin, self.frequency)

        self.timeout = timedelta(seconds=30) #timeout after 30 seconds
        self.purpose = None #Unused, may implement to handle light behavior when multiple sources have claim to control

        self.t = threading.Thread(target=self.slide, args=[0.01,0,0,1])
        self.q = queue.Queue()

        self.t.start()

    def on(self):
        pins.write(self.pin, 1)

    def off(self):
        pins.write(self.pin, 0)

    def slide(self, period, final=None, initial=None, cycles=0): #internal function to handle threaded commands
        if initial is None:
            initial = pins.get_PWM_dutycycle(self.pin)
        if final is None:
            final = self.range
        if cycles < 1:
            cycles = -1
        if(final != initial):
            step_delay = period/abs(final-initial)
        else:
            step_delay = period #TODO refactor to modulate step amount rather than step delay

        timeout = datetime.now() + self.timeout
        reversed = False
        i = initial
        while(cycles != 0):
            if(final != initial):
                if((final > initial) != reversed): #if value should be moving positive, regardless of toward final or initial (XOR)
                    i = i+1
                else:
                    i = i-1
            pins.set_PWM_dutycycle(self.pin, i) #change output

            if(i == final or i == initial): #check for end of cycle
                reversed = not reversed
                if(cycles != -1):
                    cycles = cycles - 1

            time.sleep(step_delay) #delay
            if(cycles < 0): #this makes any command with limited cycles blocking; any with unlimited, non blocking. consider adding a blocking boolian argument
                try: #check for a new command
                    vars = self.q.get(False)
                    self.slide(vars[0], vars[1], vars[2], vars[3]) #slide with new parameters
                    break #allow this slide to end once the one that was just initiated does
                except queue.Empty:
                    pass
            if timeout < datetime.now(): #handle timeout for infinite loops
                pins.set_PWM_dutycycle(self.pin, 0)
                break
        if pins.get_PWM_dutycycle(self.pin) != 0:
            if timeout > datetime.now(): #handle timeout for finite commands
                try: #check for a new command
                    vars = self.q.get(True, (timeout - datetime.now()).total_seconds())
                    self.slide(vars[0], vars[1], vars[2], vars[3]) #slide with new parameters
                except queue.Empty:
                    pins.set_PWM_dutycycle(self.pin, 0)
        vars = self.q.get()
        self.slide(vars[0], vars[1], vars[2], vars[3]) #slide with new parameters

    def pulse(self, period, final=None, initial=None, cycles=0): #external function to queue commands
        if final is None:
            final = self.range
        if cycles < 1:
            cycles = -1

        self.q.put([period, final, initial, cycles])

    #TODO add function that slides from current to final once, then between final and a specified initial


# TEST CASES
#
#0: bell.ring([.9,.9,.3,.3])	ring 2 long, 2 short, repeating forever every 8 seconds
#1: bell.ring([.9,.9,.3,.3], 6, 4)    ring 2 long, 2 short, repeating 4 times every 6 seconds
#2: 
#3: 


class Bell:
    def __init__(self, pin):
        pins.set_mode(pin, pigpio.OUTPUT)
        self.pin = pin

        self.delay = 0.1
        self.min_interval = 2
        self.timeout = timedelta(seconds=30) #only allow to ring for 30 seconds

        self.purpose = None #Unused, may implement to handle light behavior when multiple sources have claim to control

        self.t = threading.Thread(target=self.process_ring, args=[[0], self.delay, 1])
        self.q = queue.Queue()

        self.t.start()

    def start(self):
        pins.write(self.pin, 1)

    def stop(self):
        pins.write(self.pin, 0)

    def process_ring(self, code=[0], period=8, cycles=0):
        if len(code) == 0: #not sure if this is needed, but adding for now
            code = [0]
        if cycles <= 0:
            cycles = -1
        if code == [0]:
            cycles = 1
        edges = []
        i = 0
        for c in code: #create a list of edges to the ring
            if c > 0: #for typical "pulse for this long" commands
                edges.append([1, i])
                i = i + round(c/self.delay)
                edges.append([0, i])
                i = i + round(c/(2*self.delay)) #sets delay until next pulse as half of pulse length
            else:
                edges.append([0, i])
        if i < period/self.delay:
            i = period/self.delay
        else:
            i = i + self.min_interval/self.delay
        edges.append([0, i])
        print(edges)
        timeout = datetime.now() + self.timeout
        i = 0
        c = 0
        while cycles != 0: #process the ringing
            while i == edges[c][1]:
                pins.write(self.pin, edges[c][0])
                c = c+1
            i = i+1
            time.sleep(self.delay)
            if i == edges[-1][1]:
                i = 0
                c = 0
                if cycles > 0:
                    cycles = cycles - 1
            try: #check for a new command
                vars = self.q.get(False)
                self.process_ring(vars[0], vars[1], vars[2]) #ring with new parameters
                break #allow this ring to end once the one that was just initiated does
            except queue.Empty:
                pass
            if timeout < datetime.now():
                pins.write(self.pin, 0)
                break
        vars = self.q.get()
        self.process_ring(vars[0], vars[1], vars[2]) #ring with new parameters

    def ring(self, code, period=8, cycles=0):
        #code processing, including TODO rounding lengths to multiples of self.delay
        print('rung with: ' + str([code, period, cycles]))
        self.q.put([code, period, cycles])

    def party_ring(self, code, period=8, cycles=0): #wrapper for ring() that takes code in a traditional format (e.g. 93R22)
        pass




class ComboEncoder:
    def __init__(self, apin, bpin, pulses):
        pins.set_mode(apin, pigpio.INPUT)
        pins.set_mode(bpin, pigpio.INPUT)
        self.apin = apin
        self.bpin = bpin
        self.a = pins.read(self.apin)
        self.b = pins.read(self.bpin)

        self.pulses = pulses

        self.QEM = [0,-1,1,2,1,0,2,-1,-1,2,0,1,2,1,-1,0] #private
        self.buffer = 0 #private

        self.combo_breaker = 0.7 #timeout that causes a combo to be ended, recognized, and executed
        self.combo = []
        self.tolerance = round(self.pulses/8 + 0.5) #rounding up here could create conflicts, but commands shouldnt be too similar anyway to prevent user confusion
        self.callbacks = {}

        self.t = threading.Thread(target=self.process_combo)
        self.q = queue.Queue()
        self.t.start()

        self.cbApin = pins.callback(apin, pigpio.EITHER_EDGE, self.interupt) #self.cbApin.cancel() to cancel
        self.cbBpin = pins.callback(bpin, pigpio.EITHER_EDGE, self.interupt) #self.cbBpin.cancel() to cancel


    def interupt(self, gpio, level, tick):
        if(level<2):
            oldBinary = 2*self.a + self.b
            if(gpio==self.apin):
                self.a = level
            elif(gpio==self.bpin):
                self.b = level
            newBinary = 2*self.a + self.b
            pulse = self.QEM[oldBinary * 4 + newBinary]*-1 #multiplying by -1 to account for gears reversing direction

            if(self.buffer != 0 and abs(self.buffer + pulse) != abs(self.buffer) + abs(pulse)): #if new interupt conflicts, reset buffer
                self.buffer = pulse
            else: #if not, add tick to buffer
                self.buffer = self.buffer + pulse
                if(abs(self.buffer) == 4): #if this is the 4th identical pulse in a row, tick
                    self.buffer = 0
                    self.q.put(pulse)

    def process_combo(self): #build combo, clean combo, match it to a command, and call its function
        while True:
            self.combo = [self.q.get()]
            while True:
                try: #check for a new command
                    tick = self.q.get(True, self.combo_breaker)
                    if(abs(self.combo[-1] + tick) == abs(self.combo[-1]) + abs(tick)):
                        self.combo[-1] = self.combo[-1] + tick
                    else:
                        self.combo.append(tick)
                except queue.Empty:
                    break #combo over, break the loop
            for i in range(len(self.combo)): #filter low entries
                if(i >= len(self.combo)): #don't loop past length of list, which may have shortened
                    break
                while(self.combo[i] and abs(self.combo[i]) <= 1): #if entry is too low, filter it out as noise
                    self.combo.pop(i)
                    if(i >= len(self.combo)): #don't loop past length of list, which may have shortened
                        break

            for i in range(len(self.combo)): #merge neighbors
                if(i >= len(self.combo)): #don't loop past length of list, which may have shortened
                    break
                if(i > 0 and abs(self.combo[i] + self.combo[i-1]) == abs(self.combo[i]) + abs(self.combo[i-1])): #if entry is neither the first or last, merge neighbors
                    self.combo[i-1] = self.combo[i-1] + self.combo.pop(i)
            if abs(self.combo[-1]) <= 2: #Remove small trailing entries, which are likely the result of the encoder slipping due to gravity
                self.combo.pop(-1)
            print(self.combo) #for debugging
            ct = threading.Thread(target=self.match_callback, args=[self.combo]) #TODO simplify if non-threaded approach is desired
            ct.start()
            self.combo = []

    def match_callback(self, combo): #find an apropriate function and call it
        args_match = None #set a target to beat for number of variable sections
        best_match = None

        #enumerate through priorities (not implemented, but may implement)
        for i in self.callbacks:
            if(len(combo) == len(self.callbacks[i]['combo'])):
                current_args = []
                for j in range(len(self.callbacks[i]['combo'])):
                    if(self.callbacks[i]['combo'][j] == 0): #count sections marked as 0 (this indicates a variable section)
                        current_args.append(combo[j])
                    else:
                        if(abs(self.callbacks[i]['combo'][j] - combo[j]) <= self.tolerance): #check if section matches within tolerance
                            #print('pass') #for debugging
                            pass
                        else:
                            #print('fail') #for debugging
                            break
                    if(j+1 == len(self.callbacks[i]['combo'])):
                        if(not args_match or len(args_match) > len(current_args)): #only match the function if it beats any existing function in fewest variable sections
                            best_match = i
                            args_match = current_args
        if(best_match):
            #print(best_match) #for debugging
            if(args_match):
                self.callbacks[best_match]['function'](args_match)
            else:
                self.callbacks[best_match]['function']()

        pass

    def create_callback(self, name, combo, function): #create a callback for a function to be called when a certain combo is processed
       # if(not self.callbacks[name]):
        self.callbacks[name] = {
            'combo': combo,
            'function': function
        }

    def remove_callback(self, name):
        self.callbacks.pop(name)

    def stop(self):
        self.cbApin.cancel()
        self.cbBpin.cancel()
        pass #any cleanup code
