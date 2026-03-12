import sys
from tkinter import Tk, StringVar, Label, Frame
from tkinter.ttk import Combobox, Style
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
	root.geometry("800x600")
	
	# Create a new client (default SD/UDP mode)
	app = Client(root, serverAddr, serverPort, rtpPort, fileName)
	app.master.title("RTP Video Player")
	
	# Configure controlFrame to handle grid layout for responsive resizing
	app.controlFrame.grid_columnconfigure(0, weight=1) # Buttons container gets remaining space
	app.controlFrame.grid_columnconfigure(1, weight=0) # Mode selector stays compact
	
	# Pack the inner button container to the left inside column 0
	app.btnContainer.grid(row=0, column=0, sticky='w')
	
	# 3.3: SD/HD Mode Selection UI - integrated into control bar
	modeFrame = Frame(app.controlFrame, bg=app.BG_SECONDARY)
	modeFrame.grid(row=0, column=1, sticky='e', padx=(10, 8), pady=8)
	
	modeLabel = Label(modeFrame, text='Mode:', font=('Segoe UI', 10),
		bg=app.BG_SECONDARY, fg=app.TEXT_DIM)
	modeLabel.pack(side='left', padx=(0, 4))
	
	# Style the combobox
	style = Style()
	style.theme_use('clam')
	style.configure('Mode.TCombobox', fieldbackground=app.BG_COLOR, 
		background=app.ACCENT, foreground=app.TEXT_COLOR,
		selectbackground=app.ACCENT, selectforeground='white',
		arrowcolor=app.TEXT_COLOR)
	
	modeVar = StringVar(value='SD (UDP)')
	modeDropdown = Combobox(modeFrame, textvariable=modeVar, 
		values=['SD (UDP)', 'HD (TCP)'], state='readonly', width=12,
		style='Mode.TCombobox')
	modeDropdown.current(0)
	modeDropdown.pack(side='left')
	
	def onModeChange(event=None):
		"""Allow mode change only before SETUP."""
		if app.state == Client.INIT:
			mode = 'HD' if 'HD' in modeVar.get() else 'SD'
			app.mode = mode
			print(f"[MODE] Selected: {mode} ({'TCP' if mode == 'HD' else 'UDP'})")
			app.statusLabel.configure(text=f'Mode: {mode} ({"TCP" if mode == "HD" else "UDP"})', fg=app.TEXT_DIM)
		else:
			# Reset dropdown to current mode
			if app.mode == 'HD':
				modeDropdown.set('HD (TCP)')
			else:
				modeDropdown.set('SD (UDP)')
			print("[MODE] Cannot change mode after SETUP. Restart client to change mode.")
	
	modeDropdown.bind('<<ComboboxSelected>>', onModeChange)
	
	root.mainloop()
	