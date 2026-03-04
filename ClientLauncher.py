import sys
from tkinter import Tk, StringVar, Label
from tkinter.ttk import Combobox
from Client import Client

if __name__ == "__main__":
	try:
		serverAddr = sys.argv[1]
		serverPort = sys.argv[2]
		rtpPort = sys.argv[3]
		fileName = sys.argv[4]	
	except:
		print("[Usage: ClientLauncher.py Server_name Server_port RTP_port Video_file]\n")	
	
	root = Tk()
	
	# Create a new client (default SD/UDP mode)
	app = Client(root, serverAddr, serverPort, rtpPort, fileName)
	app.master.title("RTPClient")
	
	# 3.3: SD/HD Mode Selection UI
	modeVar = StringVar(value='SD (UDP)')
	modeLabel = Label(root, text="Mode:")
	modeLabel.grid(row=2, column=0, padx=2, pady=5)
	modeDropdown = Combobox(root, textvariable=modeVar, values=['SD (UDP)', 'HD (TCP)'], state='readonly', width=15)
	modeDropdown.current(0)
	modeDropdown.grid(row=2, column=1, columnspan=2, padx=2, pady=5)
	
	def onModeChange(event=None):
		"""Allow mode change only before SETUP."""
		if app.state == Client.INIT:
			mode = 'HD' if 'HD' in modeVar.get() else 'SD'
			app.mode = mode
			print(f"[MODE] Selected: {mode} ({'TCP' if mode == 'HD' else 'UDP'})")
		else:
			# Reset dropdown to current mode
			if app.mode == 'HD':
				modeDropdown.set('HD (TCP)')
			else:
				modeDropdown.set('SD (UDP)')
			print("[MODE] Cannot change mode after SETUP. Restart client to change mode.")
	
	modeDropdown.bind('<<ComboboxSelected>>', onModeChange)
	
	root.mainloop()
	