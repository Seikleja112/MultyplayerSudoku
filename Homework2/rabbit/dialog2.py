## An Introduction to Tkinter# dialog2.py## Copyright (c) 1997 by Fredrik Lundh## fredrik@pythonware.com# http://www.pythonware.com#from Tkinter import *import tkMessageBoximport tkSimpleDialogclass MyDialog(tkSimpleDialog.Dialog):    def body(self, master):        Label(master, text="Chat name:").grid(row=0)        Label(master, text="Members (empty for public):").grid(row=1)        self.e1 = Entry(master)        self.e2 = Entry(master)        self.title('Chat room creation')        self.e1.grid(row=0, column=1)        self.e2.grid(row=1, column=1)    def validate(self):        first = self.e1.get().strip()        second = map(lambda x: x.strip(), self.e2.get().split(','))        if not all(c.isalnum() for c in ''.join(second + [first])) or len(first) == 0 or first in second:            tkMessageBox.showwarning("Bad input", "Illegal values, please try again")            return 0        if '' in second:            second = []        self.result = first, list(set(second))        return 1    def apply(self):        pass