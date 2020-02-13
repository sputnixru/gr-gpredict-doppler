#!/usr/bin/env python
# 

from gnuradio import gr
import pmt

class MsgPairToVar(gr.sync_block):
    """
    This block will take an input message pair and allow you to set a gnuradio variable.
    """
    def __init__(self, callback):
        gr.sync_block.__init__(self, name="MsgPairToVar", in_sig=None, out_sig=None)

        self.callback = callback

        self.message_port_register_in(pmt.intern("inpair"))
        self.set_msg_handler(pmt.intern("inpair"), self.msg_handler)

    def msg_handler(self, msg):
        try:
            new_val = pmt.to_python(pmt.cdr(msg))

            self.callback(new_val)

        except Exception as e:
            gr.log.error("Error with message conversion: %s" % str(e))

    def stop(self):
        return True
