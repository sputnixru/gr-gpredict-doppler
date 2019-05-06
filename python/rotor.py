#!/usr/bin/env python
# 
# Adapted from Nagle's doppler.py
# 

from gnuradio import gr
import threading
import time
import socket
import pmt


class rotor_runner(threading.Thread):
  def __init__(self, blockclass, minEl, gpredict_host, gpredict_port, verbose):
    threading.Thread.__init__(self)

    self.gpredict_host = gpredict_host
    self.gpredict_port = gpredict_port
    self.verbose = verbose

    self.blockclass = blockclass
    self.minEl = minEl

  def run(self):
    bind_to = (self.gpredict_host, self.gpredict_port)
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(bind_to)
    server.listen(0)

    time.sleep(0.5) # TODO: Find better way to know if init is all done
    curState = False
	
    while True:
      print "[rotor] Waiting for connection on: %s:%d" % bind_to
      sock, addr = server.accept()
      print "[rotor] Connected from: %s:%d" % (addr[0], addr[1])

      cur_az = -9999.0
      cur_el = -9999.0
      
      while True:
        data = sock.recv(1024)
        if not data:
          break

        # Allow for multiple commands to have come in at once.  For instance Frequency and AOS / LOS
        data = data.rstrip('\n') # Prevent extra '' in array
        commands = data.split('\n')
        
        for curCommand in commands:
          if curCommand.startswith('P'):
            # if self.verbose: print "[rotor] Incoming rotor command: %s" % data
            rotctl=curCommand.split()
            az=float(rotctl[1])
            el=float(rotctl[2])
          
            if (cur_az != az) or (cur_el != el):
              self.blockclass.sendAzEl(az,el)
            
            if cur_az != az:
              if self.verbose: print "[rotor] New Azimuth: %f" % az
              cur_az = az
            
            if cur_el != el:
              if self.verbose: print "[rotor] New Elevation: %f" % az
            
              # deal with state based on elevation
              if (not curState) and el >= self.minEl:
                curState = True
                self.blockclass.sendState(curState)
              elif (curState and el < self.minEl):
                curState = False
                self.blockclass.sendState(curState)
              
              cur_el = el

            # Send report OK response
            sock.sendall("RPRT 0\n")
          elif curCommand.startswith('p'):
            sock.sendall("p: %.1f %.1f\n" % (cur_az,cur_el))

      sock.close()
      if self.verbose: print "[rotor] Disconnected from: %s:%d" % (addr[0], addr[1])


class rotor(gr.sync_block):
  def __init__(self, minEl, gpredict_host, gpredict_port, verbose):
    gr.sync_block.__init__(self, name = "GPredict Rotor", in_sig = None, out_sig = None)
    
    rotor_runner(self, minEl, gpredict_host, gpredict_port, verbose).start()
    
    self.message_port_register_out(pmt.intern("az_el"))
    self.message_port_register_out(pmt.intern("state"))

  def sendAzEl(self,az,el):
    meta = {}      
    meta['az'] = az
    meta['el'] = el
    self.message_port_pub(pmt.intern("az_el"),pmt.cons( pmt.to_pmt(meta), pmt.PMT_NIL ))

  def sendState(self,state):
    meta = {}  
    
    if (state):    
      meta['state'] = 1
    else:
      meta['state'] = 0
      
    self.message_port_pub(pmt.intern("state"),pmt.cons( pmt.to_pmt(meta), pmt.PMT_NIL ))
