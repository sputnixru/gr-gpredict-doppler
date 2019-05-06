#!/usr/bin/env python
'''
   Copyright 2015 Wolfgang Nagele

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.
'''
from gnuradio import gr
import threading
import time
import socket
import pmt

class doppler_runner(threading.Thread):
  def __init__(self, bc, callback, gpredict_host, gpredict_port, verbose):
    threading.Thread.__init__(self)

    self.callback = callback
    self.gpredict_host = gpredict_host
    self.gpredict_port = gpredict_port
    self.verbose = verbose
    self.blockclass = bc

  def run(self):
    bind_to = (self.gpredict_host, self.gpredict_port)
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(bind_to)
    server.listen(0)

    time.sleep(0.5) # TODO: Find better way to know if init is all done

    while True:
      if self.verbose: print "Waiting for connection on: %s:%d" % bind_to
      sock, addr = server.accept()
      if self.verbose: print "[doppler] Connected from: %s:%d" % (addr[0], addr[1])

      cur_freq = 0
      while True:
        data = sock.recv(1024)
        if not data:
          break

        if data.startswith('F'):
          freq = int(data[1:].strip())
          if cur_freq != freq:
            if self.verbose: print "New frequency: %d" % freq
            self.callback(freq)
            self.blockclass.sendFreq(freq)
            cur_freq = freq
          sock.sendall("RPRT 0\n")
        elif data.startswith('f'):
          sock.sendall("f: %d\n" % cur_freq)
        elif data.startswith('AOS'):
          # Received Acquisition of signal.  Send state up
          self.blockclass.sendState(True)
        elif data.startswith('LOS'):
          # Received loss of signal.  Send state down
          self.blockclass.sendState(False)
        else:
          print "[doppler] received unknown command: %s" % data

      sock.close()
      if self.verbose: print "Disconnected from: %s:%d" % (addr[0], addr[1])


class doppler(gr.sync_block):
  def __init__(self, callback, gpredict_host, gpredict_port, verbose):
    gr.sync_block.__init__(self, name = "GPredict Doppler", in_sig = None, out_sig = None)
    
    # Init block variables
    doppler_runner(self, callback, gpredict_host, gpredict_port, verbose).start()
    self.message_port_register_out(pmt.intern("freq"))
    self.message_port_register_out(pmt.intern("state"))

  def sendFreq(self,freq):
    p = pmt.from_float(freq)
    self.message_port_pub(pmt.intern("freq"),p)
    
  def sendState(self,state):
    meta = {}  
    
    if (state):    
      meta['state'] = 1
    else:
      meta['state'] = 0
      
    self.message_port_pub(pmt.intern("state"),pmt.cons( pmt.to_pmt(meta), pmt.PMT_NIL ))
    