#!/usr/bin/env python
# 
# 
# 

from gnuradio import gr
import sys
import threading
import time
import socket
import pmt

# NOTE FOR DOPPLER CALCULATION:
# Negative velocities are towards you,
# Positive velocities are away from you.

def doppler_shift(frequency, relativeVelocity):
    """
    DESCRIPTION:
        This function calculates the doppler shift of a given frequency when actual
        frequency and the relative velocity is passed.
        The function for the doppler shift is f' = f - f*(v/c).
    INPUTS:
        frequency (float)        = satlitte's beacon frequency in Hz
        relativeVelocity (float) = Velocity at which the satellite is moving
                                   towards or away from observer in m/s
    RETURNS:
        Param1 (float)           = The frequency experienced due to doppler shift in Hz
    AFFECTS:
        None
    EXCEPTIONS:
        None
    DEPENDENCIES:
        ephem.Observer(...), ephem.readtle(...)
    Note: relativeVelocity is positive when moving away from the observer
          and negative when moving towards
    """
    return  (frequency - frequency * (relativeVelocity/3e8)) 

class doppler_runner(threading.Thread):
  def __init__(self, blockclass, verbose):
    threading.Thread.__init__(self)

    self.verbose = verbose
    
    self.blockclass = blockclass

    self.gpredict_host = blockclass.host
    self.gpredict_port = blockclass.port

    self.stopThread = False
    self.clientConnected = False
    self.sock = None
    
  def run(self):
    try:
      bind_to = (self.gpredict_host, self.gpredict_port)
      self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
      self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
      self.server.bind(bind_to)
      self.server.listen(0)
    except Exception as e:
      print("[vel_doppler] Error starting listener: %s" % str(e))
      sys.exit(1)
          
    time.sleep(0.5) # TODO: Find better way to know if init is all done
    # Calculate velocity-shifted frequency and send initial messages
    self.blockclass.currentFrequency = doppler_shift(self.blockclass.knownFrequency, self.blockclass.initialVelocity)
    self.blockclass.sendFrequency(self.blockclass.currentFrequency)
    self.blockclass.sendFrequencyShift(self.blockclass.currentFrequency-self.blockclass.knownFrequency)
    
    while not self.stopThread:
      print("[vel_doppler] Waiting for connection on: %s:%d" % bind_to)
      self.clientConnected = False
      self.sock, addr = self.server.accept()
      self.clientConnected = True
      print("[vel_doppler] Connected from: %s:%d" % (addr[0], addr[1]))

      while not self.stopThread:
        try:
          data = self.sock.recv(1024)
        except:
          data = None
          
        if not data or self.stopThread:
          break

        # Allow for multiple commands to have come in at once.  For instance Frequency and AOS / LOS
        data = data.decode('ASCII').rstrip('\n') # Prevent extra '' in array
        commands = data.split('\n')
        
        for curCommand in commands:
          if curCommand.startswith('V'):
            v_ctl=curCommand.split()
            vel=float(v_ctl[1])
          
            if (self.blockclass.curVel != vel):
              if self.verbose: print("[vel_doppler] New Velocity: %f" % vel)
              # Calc new frequencies
              self.blockclass.curVel = vel
              self.blockclass.currentFrequency = doppler_shift(self.blockclass.knownFrequency, vel)
              self.blockclass.sendFreqency(self.blockclass.currentFrequency)
              shift = self.blockclass.currentFrequency - self.blockclass.knownFrequency 
              self.blockclass.sendFrequencyShift(shift)
            
            # Send report OK response
            try:
              self.sock.sendall("RPRT 0\n".encode("UTF-8"))
            except:
              pass
          elif curCommand.startswith('v'):
            try:
                # Returns velocity frequency
              sendMsgStr = "v: %.1f %.1f\n" % (self.blockclass.curVel,self.blockclass.currentFrequency )
              self.sock.sendall(sendMsgStr.encode("UTF-8"))
            except:
              pass
          elif curCommand == 'q':
            # Disconnect
            # Send report OK response
            try:
              self.sock.sendall("RPRT 0\n".encode("UTF-8"))
            except:
              pass   
          else:
            print("[vel_doppler] Unknown command: %s" % curCommand)
            # Send report OK response
            try:
              self.sock.sendall("RPRT 0\n".encode("UTF-8"))
            except:
              pass   

      self.sock.close()
      self.clientConnected = False
      self.sock = None
      if self.verbose: print("[vel_doppler] Disconnected from: %s:%d" % (addr[0], addr[1]))

    # print "[rotor] Shutting down server."
    self.server.shutdown(socket.SHUT_RDWR)
    self.server.close()
    self.server = None

class vel_doppler(gr.sync_block):
  def __init__(self, knownFrequency, initVelocity, host, port, verbose):
    gr.sync_block.__init__(self, name = "GPredict Velocity Doppler", in_sig = None, out_sig = None)
    
    self.host = host
    self.port = port
    
    self.knownFrequency = knownFrequency
    self.currentFrequency = knownFrequency
    
    self.initialVelocity = initVelocity
    self.curVel = initVelocity

    # Inbound velocity message on port
    self.message_port_register_in(pmt.intern("velocity"))
    self.set_msg_handler(pmt.intern("velocity"), self.velMsgHandler)   
   
   # Output ports - straight frequency for the velocity, and the frequency shift
    self.message_port_register_out(pmt.intern("frequency"))
    self.message_port_register_out(pmt.intern("freqshift"))
    
    # Now start thread for external velocity control
    self.thread = doppler_runner(self, verbose)
    self.thread.start()
    

  def velMsgHandler(self, pdu):
    try:    
      newVelocity = pmt.to_python(pmt.cdr(pdu))
      
      self.curVel = newVelocity
      
      self.currentFrequency = doppler_shift(self.knownFrequency, newVelocity)
      self.sendFrequency(self.currentFrequency)
      self.sendFrequencyShift(self.currentFrequency-self.knownFrequency)
      
    except Exception as e:
      print("[vel_doppler] Error with velocity message: %s" % str(e))
      print(str(newVelocity) )

  def stop(self):
    self.thread.stopThread = True
    if self.thread.clientConnected:
      self.thread.sock.close()
    else:
      # Have to force a connection to unblock the accept
      try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect(("localhost",self.port))
        time.sleep(0.1)
        self.sock.shutdown(socket.SHUT_RDWR)
        s.close()
      except:
        pass
      
    self.thread.join()
        
    return True
    
  def sendFrequency(self,freq):
    self.message_port_pub(pmt.intern("frequency"),pmt.cons( pmt.intern("freq"), pmt.from_double(freq) ))

  def sendFrequencyShift(self,freqshift):
    self.message_port_pub(pmt.intern("freqshift"),pmt.cons( pmt.intern("freq"), pmt.from_double(freqshift) ))
