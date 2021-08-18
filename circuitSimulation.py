import asyncio
from datetime import datetime as dt


async def timed_call(timeout,callback,duration=5,args=None):
    loop = asyncio.get_running_loop()
    end_time = loop.time() + duration
    while timeout>0:
        if loop.is_running():
            if args is not None:
                callback(args)
            else:
                callback()
            await asyncio.sleep(timeout)
            if (loop.time() ) >= end_time+.01:
                break

class Circuit():
    """ Simulation object of an electric circuit"""
    def __init__(self,rmax=100,rl=30,r1=0,vs=10,timeout=0.01,duration=10,print_timeout=.1):
        """
        params:
            rmax: float
                maximum value of r1 and r2
            rl: float  
                load resistor in parallel to voltmeter
            r1:
                starting value of r1. r2 is derived as difference from the maximum.
            timeout: float
                update frequency of the circuit
            duration:
                time before ending simulation
            print_timeout: float
                frequency of printout of the internal values, r1,r2,A and V              
        """

        self.vs = vs
        self.rmax = rmax
        self.rl = rl

        self._r1 = r1

        # asyncio
        self.t0 = None
        self.timeout = timeout
        self.print_timeout = print_timeout
        self.connected_devices = []
        self.loop = None
        self.duration = duration

    @property
    def r1(self):
        return self._r1
    @r1.setter
    def r1(self,val):
        self._r1 = min(max(0,val),self.rmax)

    @property
    def r2(self):
        return self.rmax - self.r1

    @property
    def rp(self):
        return (self.r2 * self.rl) / (self.r2 + self.rl)

    @property
    def amp(self):
        return self.volt / self.rl

    @property
    def volt(self):
        return self.vs * (1-self.r1/(self.r1 + self.rp))

    def print_resistor_values(self):
        "print the current values of r1 and r2"
        print(f'{dt.now()} | Circuit: r1 = {self.r1:.0f} k\u03A9 | r2 = {self.r2:.0f} k\u03A9')

    def print_ampvolt(self):
        "print the current values of r1 and r2"
        print(f'{dt.now()} | Circuit: {self.amp:3.3f} A | {self.volt:3.3f} V ')

    def update(self):
        "update the resistor values based on the time passed since the start of the simulation"
        t = self.loop.time() - self.t0
        self.r1 = min(10*t,self.rmax)

    def start(self):
        """start or restart the simulation"""
        asyncio.run(self._run_simulation())

    async def _run_simulation(self):
        
        print(f'{dt.now()} | starting simulation')
        self.loop = asyncio.get_running_loop()
        self.t0 = self.loop.time()
        tasks = []
        tasks.append(timed_call(0.05, self.update, duration=self.duration))
        tasks.append(timed_call(self.print_timeout,self.print_ampvolt,duration=self.duration))
        tasks.append(timed_call(self.print_timeout,self.print_resistor_values,duration=self.duration))

        for dev in self.connected_devices:
            tasks.append(timed_call(dev.timeout,dev.read,duration=self.duration))

        await asyncio.gather(*tasks)



class Device():
    """ Class representing a generic measurement device to be connected to the simulation circuit"""
    def __init__(self,circuit=None,timeout=.1):
        """
        params:
            circuit: Circuit
                circuit simulation object to connect to
            timeout: 
                reading frequency of values from the circuit
        """
        self.values = []
        self.unit = None
        if circuit is not None:
            self.connect(circuit)
        else:
            self.circuit = None
        self.parameter = None
        self.timeout = timeout
        self.name = 'generic device'

        self.child_devices = []


    def reset_memory(self):
        self.values = []

    def connect(self,circuit):
        self.circuit = circuit
        self.circuit.connected_devices.append(self)

    def disconnect(self):
        self.circuit = None
    
    def read(self):
        """ Read action, to be called by the simulation"""
        if circuit is None:
            print('connect the {name} to a circuit to read its values')
        else:
            value = getattr(self.circuit,self.parameter)
            when = dt.now()
            vtup= (when,value)
            self.values.append(vtup)
            for dev in self.child_devices:
                # tell eventual connected ohmmeters that the values changed.
                dev._update(self.name,vtup)
            print(f'{vtup[0]} | {self.name}: {vtup[1]:.3f} {self.unit}')

    def print_last(self):
        if len(self.values) == 0:
            print('no values measured yet...')
        else:
            last = self.values[-1]
            print(f'{last[0]}: {last[1]:.2f} {self.unit}')

class Voltmeter(Device):
    """a Voltmeter"""
    def __init__(self,circuit=None,timeout=0.1):
        super(Voltmeter,self).__init__(circuit=circuit,timeout=timeout)
        self.unit = 'V'
        self.name = 'voltmeter'
        self.parameter = 'volt'

class Ammeter(Device):
    """an Ammeter"""
    def __init__(self,circuit=None,timeout=0.1):
        super(Ammeter,self).__init__(circuit=circuit,timeout=timeout)
        self.unit = 'A'
        self.name = 'ammeter'
        self.parameter = 'amp'

class Ohmmeter():
    """an Ohmmeter based on ammeter and voltmeter."""
    def __init__(self,ammeter=None,voltmeter=None,timeout=1,mode='last',window=2):
        """
        params:
            ammeter: Ammeter
                ammeter object, connected to the simulation circuit
            voltmeter: Voltmeter
                Voltmeter object, connected to the simulation circuit
            timeout: 
                reading frequency of values from the ammeter and voltmeter
            mode: str
                value representation method: 
                - if 'last' prints the last values obtained from the connected devices,
                - if 'rolling' it prints the average value of the last n seconds, defined by "window"
            window:
                time window of the rolling average function
            """
        self.ammeter = None
        self.voltmeter = None
        if ammeter is not None:
            self.connect('ammeter',ammeter)
        if voltmeter is not None:
            self.connect('voltmeter',voltmeter)
        self.timeout = timeout
        self.mode = mode
        self.window = window

        self.ammeter_values = []
        self.voltmeter_values = []
        self.connect_circuit()


    def connect(self,name,device):
        """connect to an ammeter or voltmeter"""
        if hasattr(self,name):
            setattr(self,name,device)
            getattr(self,name).child_devices.append(self)
        else:
            raise ValueError(f'{name} is not a valid device, use "ammeter" or "voltmeter".')
        self.connect_circuit()

    def _update(self,name,val):
        """ internal function to recieve changes of the value of the connected devices"""
        l = getattr(self,f'{name}_values')
        l.append(val)

    def connect_circuit(self):
        """ connect to the circuit simulation"""
        if self.ammeter is not None and self.voltmeter is not None:
            if self.ammeter.circuit != self.voltmeter.circuit:
                raise VauleError('Ammeter and voltmeter belong to different circuits!')
            else:
                self.circuit = self.ammeter.circuit
                self.circuit.connected_devices.append(self)

    def read(self):
        """ Read action, to be called by the simulation"""
        if self.mode == 'last':
            val = self.last_rl
        elif self.mode == 'rolling':
            val = self.mean_rl
        if len(self.ammeter_values)>0 and len(self.voltmeter_values)>0 and val:
            print(f'{dt.now()} | Ohmmeter ({self.mode}):  {val:.3f} k\u03A9')
        else:
            print('Ohmmeter: not enough data in memory')

    @property
    def last_rl(self):
        I = self.ammeter_values[-1][1]
        V = self.voltmeter_values[-1][1]
        return V/I

    @property
    def mean_rl(self):
        t0 = dt.now()       
        aVal,aCount = 0.0,0
        vVal,vCount = 0.0,0
        for tpl in self.ammeter_values:
            if (t0-tpl[0]).seconds > self.window:
                aVal += tpl[1]
                aCount +=1

        for tpl in self.voltmeter_values:
            if (t0-tpl[0]).seconds > self.window:
                vVal += tpl[1]
                vCount +=1
        try:
            aMean = aVal/aCount
            vMean = vVal/vCount
            return vMean/aMean
        except ZeroDivisionError:
            return None


if __name__ == "__main__":

    print('#####################################\n',
          '        Starting Simulation          \n',
          '#####################################\n')
    t0 = dt.now()
    # initialize the simulation with the given starting condition
    circuit = Circuit(rmax=100, rl=30, r1=0, vs=10, timeout=0.01, duration=10, print_timeout=.1)
    # create an ammeter and a voltmeter, and connect them to the circuit
    ammeter = Ammeter(circuit=circuit,timeout=.3)
    voltmeter = Voltmeter(circuit=circuit,timeout=.1)
    # create two ohmmeters, 
    # - one reading the last values each second, 
    ohmmeter = Ohmmeter(ammeter=ammeter,voltmeter=voltmeter,mode='last',timeout=1)
    # - one reporting a rolling average over the last 2 seconds
    ohmmeter_avg = Ohmmeter(ammeter=ammeter,voltmeter=voltmeter,mode='rolling',timeout=2)
    # Start the event loop of the simulation
    circuit.start()
    print('simulation complete')
    
    # The simulation can be restarted and will reset to its original starting condition
    circuit.start()
    print('second simulation iteration complete')