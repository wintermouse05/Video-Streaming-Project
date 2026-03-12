from tkinter import *
import tkinter.messagebox
from tkinter import ttk
from PIL import Image, ImageTk
import socket, threading, sys, traceback, os
import time as time_module
from collections import deque
import struct
import io

from RtpPacket import RtpPacket

CACHE_FILE_NAME = "cache-"
CACHE_FILE_EXT = ".jpg"
BUFFER_SIZE = 10  # Number of frames to buffer before displaying (3.1)

class Client:
	INIT = 0
	READY = 1
	PLAYING = 2
	state = INIT
	
	SETUP = 0
	PLAY = 1
	PAUSE = 2
	TEARDOWN = 3
	DESCRIBE = 4
	
	# Initiation..
	def __init__(self, master, serveraddr, serverport, rtpport, filename, mode='SD'):
		self.master = master
		self.master.protocol("WM_DELETE_WINDOW", self.handler)
		self.createWidgets()
		self.serverAddr = serveraddr
		self.serverPort = int(serverport)
		self.rtpPort = int(rtpport)
		self.fileName = filename
		self.rtspSeq = 0
		self.sessionId = 0
		self.requestSent = -1
		self.teardownAcked = 0
		self.connectToServer()
		self.frameNbr = 0
		
		# 3.3: SD/HD Mode
		self.mode = mode  # 'SD' for UDP, 'HD' for TCP
		self.tcpConnected = False
		
		# 3.1: Frame Buffer Queue
		self.frameBuffer = deque()
		self.bufferReady = False
		
		# 3.4: FPS Monitor
		self.fpsCounter = 0
		self.fpsStartTime = time_module.time()
		
		# 3.5: Packet Loss Detection
		self.expectedSeqNum = 1
		self.lostPackets = 0
		self.totalPackets = 0
		
		# 2.6: Fragment reassembly buffer
		self.fragmentBuffer = bytearray()
		
	def createWidgets(self):
		"""Build modern GUI with auto-scaling video."""
		# Configure dark theme colors
		self.BG_COLOR = '#1e1e2e'
		self.BG_SECONDARY = '#2a2a3d'
		self.ACCENT = '#475569'
		self.ACCENT_HOVER = '#334155'   
		self.TEXT_COLOR = '#e2e8f0'
		self.TEXT_DIM = '#94a3b8'
		self.BORDER_COLOR = '#374151'
		self.SUCCESS = '#22c55e'
		self.DANGER = '#ef4444'
		self.WARNING = '#f59e0b'
		
		self.master.configure(bg=self.BG_COLOR)
		self.master.minsize(640, 480)
		
		# Make the video area expand to fill window
		self.master.grid_rowconfigure(0, weight=1)
		self.master.grid_columnconfigure(0, weight=1)
		
		# === Video Display Area (row 0) - takes most space ===
		self.videoFrame = Frame(self.master, bg='#000000', bd=0, highlightthickness=1, highlightbackground=self.BORDER_COLOR)
		self.videoFrame.grid(row=0, column=0, sticky='nsew', padx=8, pady=(8, 4))
		self.videoFrame.grid_rowconfigure(0, weight=1)
		self.videoFrame.grid_columnconfigure(0, weight=1)
		
		self.label = Label(self.videoFrame, bg='#000000', text='⏵  Press Setup to begin', 
			fg=self.TEXT_DIM, font=('Segoe UI', 14), anchor='center')
		self.label.grid(row=0, column=0, sticky='nsew')
		
		# === Control Bar (row 1) - compact buttons ===
		self.controlFrame = Frame(self.master, bg=self.BG_SECONDARY, bd=0, 
			highlightthickness=1, highlightbackground=self.BORDER_COLOR)
		self.controlFrame.grid(row=1, column=0, sticky='ew', padx=8, pady=4)
		
		# Button styling
		btn_font = ('Segoe UI', 10, 'bold')
		btn_padx = 16
		btn_pady = 6
		
		# Define a flexible inner frame for buttons to keep them left-aligned
		self.btnContainer = Frame(self.controlFrame, bg=self.BG_SECONDARY)
		self.btnContainer.pack(side=LEFT, fill=X, expand=True)
		
		# Setup button
		self.setup = Button(self.btnContainer, text='⚙ Setup', font=btn_font,
			bg=self.ACCENT, fg='white', activebackground=self.ACCENT_HOVER, activeforeground='white',
			bd=0, padx=btn_padx, pady=btn_pady, cursor='hand2', command=self.setupMovie)
		self.setup.pack(side=LEFT, padx=(8, 4), pady=8)
		
		# Play button
		self.start = Button(self.btnContainer, text='▶ Play', font=btn_font,
			bg=self.ACCENT, fg='white', activebackground=self.ACCENT_HOVER, activeforeground='white',
			bd=0, padx=btn_padx, pady=btn_pady, cursor='hand2', command=self.playMovie)
		self.start.pack(side=LEFT, padx=4, pady=8)
		
		# Pause button
		self.pause = Button(self.btnContainer, text='⏸ Pause', font=btn_font,
			bg=self.ACCENT, fg='white', activebackground=self.ACCENT_HOVER, activeforeground='white',
			bd=0, padx=btn_padx, pady=btn_pady, cursor='hand2', command=self.pauseMovie)
		self.pause.pack(side=LEFT, padx=4, pady=8)
		
		# Teardown button
		self.teardown = Button(self.btnContainer, text='⏹ Teardown', font=btn_font,
			bg=self.ACCENT, fg='white', activebackground=self.ACCENT_HOVER, activeforeground='white',
			bd=0, padx=btn_padx, pady=btn_pady, cursor='hand2', command=self.exitClient)
		self.teardown.pack(side=LEFT, padx=4, pady=8)
		
		# Describe button
		self.describe = Button(self.btnContainer, text='ℹ Describe', font=btn_font,
			bg=self.ACCENT, fg='white', activebackground=self.ACCENT_HOVER, activeforeground='white',
			bd=0, padx=btn_padx, pady=btn_pady, cursor='hand2', command=self.describeMovie)
		self.describe.pack(side=LEFT, padx=4, pady=8)
		
		# === Status Bar (row 2) - FPS, buffer, loss ===
		self.statusFrame = Frame(self.master, bg=self.BG_SECONDARY, bd=0,
			highlightthickness=1, highlightbackground=self.BORDER_COLOR)
		self.statusFrame.grid(row=2, column=0, sticky='ew', padx=8, pady=(0, 8))
		
		status_font = ('Consolas', 9)
		self.statusLabel = Label(self.statusFrame, text='Status: Idle', font=status_font,
			bg=self.BG_SECONDARY, fg=self.TEXT_DIM, anchor='w', padx=10, pady=4)
		self.statusLabel.pack(side=LEFT, fill=X, expand=True)
		
		self.fpsLabel = Label(self.statusFrame, text='FPS: --', font=status_font,
			bg=self.BG_SECONDARY, fg=self.SUCCESS, anchor='e', padx=10, pady=4)
		self.fpsLabel.pack(side=RIGHT)
	
	def setupMovie(self):
		"""Setup button handler."""
		if self.state == self.INIT:
			self.sendRtspRequest(self.SETUP)
	
	def describeMovie(self):
		"""Describe button handler - request stream info from server."""
		self.sendRtspRequest(self.DESCRIBE)
	
	def exitClient(self):
		"""Teardown button handler."""
		# 3.5: Print final packet loss stats
		if self.totalPackets > 0:
			totalExpected = self.totalPackets + self.lostPackets
			lossRate = (self.lostPackets / totalExpected) * 100
			print(f"\n{'='*50}")
			print(f"[STATS] Session Summary ({self.mode} mode - {'TCP' if self.mode == 'HD' else 'UDP'}):")
			print(f"  Total packets received: {self.totalPackets}")
			print(f"  Packets lost: {self.lostPackets}")
			print(f"  Packet loss rate: {lossRate:.2f}%")
			print(f"{'='*50}\n")
		
		self.sendRtspRequest(self.TEARDOWN)
		self.master.destroy()
		
		try:
			os.remove(CACHE_FILE_NAME + str(self.sessionId) + CACHE_FILE_EXT)
		except:
			pass
		
		# Close TCP server socket if HD mode
		if self.mode == 'HD' and hasattr(self, 'rtpServerSocket'):
			try:
				self.rtpServerSocket.close()
			except:
				pass

	def pauseMovie(self):
		"""Pause button handler."""
		if self.state == self.PLAYING:
			self.sendRtspRequest(self.PAUSE)
	
	def playMovie(self):
		"""Play button handler."""
		if self.state == self.READY:
			# Create a new thread to listen for RTP packets
			threading.Thread(target=self.listenRtp).start()
			self.playEvent = threading.Event()
			self.playEvent.clear()
			self.sendRtspRequest(self.PLAY)
			
			# 3.1: Reset buffer state
			if len(self.frameBuffer) > 0:
				self.bufferReady = True  # Resume with existing buffer
			else:
				self.bufferReady = False
			
			# 3.4: Reset FPS counter
			self.fpsCounter = 0
			self.fpsStartTime = time_module.time()
			
			# Start display loop from buffer
			self.master.after(100, self.displayFromBuffer)
	
	def listenRtp(self):		
		"""Listen for RTP packets and add to frame buffer."""
		# 3.3: For TCP/HD mode, accept connection on first PLAY
		if self.mode == 'HD' and not self.tcpConnected:
			try:
				self.rtpServerSocket.settimeout(10)
				self.rtpSocket, _ = self.rtpServerSocket.accept()
				self.rtpSocket.settimeout(0.5)
				self.tcpConnected = True
				print("[TCP] RTP data connection established")
			except Exception as e:
				print(f"[ERROR] TCP accept failed: {e}")
				return
		
		while True:
			try:
				if self.mode == 'HD':
					# TCP mode: read length-prefixed RTP packets
					lengthBytes = self.recvExact(self.rtpSocket, 4)
					if lengthBytes is None:
						if self.playEvent.isSet() or self.teardownAcked == 1:
							break
						continue
					length = struct.unpack('>I', lengthBytes)[0]
					data = self.recvExact(self.rtpSocket, length)
					if data is None:
						if self.playEvent.isSet() or self.teardownAcked == 1:
							break
						continue
				else:
					# UDP mode (original behavior)
					data = self.rtpSocket.recv(20480)
				
				if data:
					rtpPacket = RtpPacket()
					rtpPacket.decode(data)
					
					currFrameNbr = rtpPacket.seqNum()
					print("Current Seq Num: " + str(currFrameNbr))
					
					# 3.5: Packet Loss Detection
					if currFrameNbr > self.expectedSeqNum:
						lost = currFrameNbr - self.expectedSeqNum
						self.lostPackets += lost
						print(f"[PACKET LOSS] Lost {lost} packet(s): expected seq {self.expectedSeqNum}, got {currFrameNbr}")
					if currFrameNbr >= self.expectedSeqNum:
						self.expectedSeqNum = currFrameNbr + 1
					self.totalPackets += 1
					
					if currFrameNbr > self.frameNbr: # Discard the late packet
						self.frameNbr = currFrameNbr
						# 2.6: Fragment reassembly based on Marker bit
						self.fragmentBuffer.extend(rtpPacket.getPayload())
						
						if rtpPacket.marker() == 1:
							# Marker=1 means last fragment of the frame → complete frame
							self.frameBuffer.append(bytes(self.fragmentBuffer))
							self.fragmentBuffer = bytearray()
						else:
							# Marker=0 means more fragments coming, keep accumulating
							pass
			except socket.timeout:
				# Timeout is normal - check stop conditions
				if self.playEvent.isSet():
					break
				if self.teardownAcked == 1:
					try:
						self.rtpSocket.shutdown(socket.SHUT_RDWR)
						self.rtpSocket.close()
					except:
						pass
					break
				continue
			except:
				# Stop listening upon requesting PAUSE or TEARDOWN
				if self.playEvent.isSet(): 
					break
				
				# Upon receiving ACK for TEARDOWN request,
				# close the RTP socket
				if self.teardownAcked == 1:
					try:
						self.rtpSocket.shutdown(socket.SHUT_RDWR)
						self.rtpSocket.close()
					except:
						pass
					break
	
	def recvExact(self, sock, n):
		"""Receive exactly n bytes from a TCP socket (3.3 HD mode helper)."""
		data = b''
		while len(data) < n:
			if self.playEvent.isSet() or self.teardownAcked == 1:
				return None
			try:
				chunk = sock.recv(n - len(data))
				if not chunk:
					return None
				data += chunk
			except socket.timeout:
				continue
		return data
	
	def displayFromBuffer(self):
		"""Display frames from the buffer queue (3.1 + 3.2 + 3.4)."""
		if self.playEvent.isSet() or self.teardownAcked == 1:
			return
		
		# 3.1: Wait for buffer to fill before first display
		if not self.bufferReady:
			if len(self.frameBuffer) >= BUFFER_SIZE:
				self.bufferReady = True
				print(f"[BUFFER] Initial buffering complete ({BUFFER_SIZE} frames)")
				self.statusLabel.configure(text=f'Status: Playing ({self.mode} mode)', fg=self.SUCCESS)
			else:
				# Still buffering, check again later
				bufPct = int(len(self.frameBuffer) / BUFFER_SIZE * 100)
				self.statusLabel.configure(text=f'Buffering... {bufPct}% ({len(self.frameBuffer)}/{BUFFER_SIZE})', fg=self.WARNING)
				self.master.after(50, self.displayFromBuffer)
				return
		
		if len(self.frameBuffer) > 0:
			frame = self.frameBuffer.popleft()
			self.updateMovie(self.writeFrame(frame))
			
			# 3.4: FPS Monitor
			self.fpsCounter += 1
			now = time_module.time()
			elapsed = now - self.fpsStartTime
			if elapsed >= 1.0:
				fps = self.fpsCounter / elapsed
				print(f"[FPS] {fps:.1f} frames/sec | Buffer: {len(self.frameBuffer)} | Lost: {self.lostPackets}")
				# Update GUI status bar
				self.fpsLabel.configure(text=f'FPS: {fps:.1f}  |  Buf: {len(self.frameBuffer)}  |  Lost: {self.lostPackets}')
				self.fpsCounter = 0
				self.fpsStartTime = now
		else:
			# 3.2: Jitter Handling - buffer underrun
			if self.bufferReady:
				print("[JITTER] Buffer underrun - pausing display temporarily")
				self.statusLabel.configure(text='Buffering... (jitter recovery)', fg=self.WARNING)
				self.bufferReady = False
		
		# Schedule next display (~20 FPS = 50ms interval)
		self.master.after(50, self.displayFromBuffer)
					
	def writeFrame(self, data):
		"""Write the received frame to a temp image file. Return the image file."""
		cachename = CACHE_FILE_NAME + str(self.sessionId) + CACHE_FILE_EXT
		file = open(cachename, "wb")
		file.write(data)
		file.close()
		
		return cachename
	
	def updateMovie(self, imageFile):
		"""Update the image file as video frame in the GUI (auto-scale to fit)."""
		try:
			img = Image.open(imageFile)
			
			# Get video frame dimensions to fit
			frame_w = self.videoFrame.winfo_width()
			frame_h = self.videoFrame.winfo_height()
			
			if frame_w > 10 and frame_h > 10:
				# Scale image to fit while maintaining aspect ratio
				img_w, img_h = img.size
				ratio = min(frame_w / img_w, frame_h / img_h)
				new_w = int(img_w * ratio)
				new_h = int(img_h * ratio)
				if new_w > 0 and new_h > 0:
					img = img.resize((new_w, new_h), Image.LANCZOS)
			
			photo = ImageTk.PhotoImage(img)
			self.label.configure(image=photo, text='')
			self.label.image = photo
		except Exception as e:
			pass  # Skip display errors silently
		
	def connectToServer(self):
		"""Connect to the Server. Start a new RTSP/TCP session."""
		self.rtspSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		try:
			self.rtspSocket.connect((self.serverAddr, self.serverPort))
		except:
			tkinter.messagebox.showwarning('Connection Failed', 'Connection to \'%s\' failed.' %self.serverAddr)
	
	def sendRtspRequest(self, requestCode):
		"""Send RTSP request to the server."""
		# Setup request
		if requestCode == self.SETUP and self.state == self.INIT:
			threading.Thread(target=self.recvRtspReply).start()
			# Update RTSP sequence number.
			self.rtspSeq += 1
			
			# 3.3: Determine transport based on mode
			if self.mode == 'HD':
				transport = 'RTP/TCP'
			else:
				transport = 'RTP/UDP'
			
			# Write the RTSP request to be sent.
			request = 'SETUP ' + self.fileName + ' RTSP/1.0\r\n' \
			          + 'CSeq: ' + str(self.rtspSeq) + '\r\n' \
			          + 'Transport: ' + transport + '; client_port= ' + str(self.rtpPort) + '\r\n\r\n'
			
			# Keep track of the sent request.
			self.requestSent = self.SETUP
		
		# Play request
		elif requestCode == self.PLAY and self.state == self.READY:
			# Update RTSP sequence number.
			self.rtspSeq += 1
			
			# Write the RTSP request to be sent.
			request = 'PLAY ' + self.fileName + ' RTSP/1.0\r\n' \
			          + 'CSeq: ' + str(self.rtspSeq) + '\r\n' \
			          + 'Session: ' + str(self.sessionId) + '\r\n\r\n'
			
			# Keep track of the sent request.
			self.requestSent = self.PLAY
		
		# Pause request
		elif requestCode == self.PAUSE and self.state == self.PLAYING:
			# Update RTSP sequence number.
			self.rtspSeq += 1
			
			# Write the RTSP request to be sent.
			request = 'PAUSE ' + self.fileName + ' RTSP/1.0\r\n' \
			          + 'CSeq: ' + str(self.rtspSeq) + '\r\n' \
			          + 'Session: ' + str(self.sessionId) + '\r\n\r\n'
			
			# Keep track of the sent request.
			self.requestSent = self.PAUSE
			
		# Teardown request
		elif requestCode == self.TEARDOWN and not self.state == self.INIT:
			# Update RTSP sequence number.
			self.rtspSeq += 1
			
			# Write the RTSP request to be sent.
			request = 'TEARDOWN ' + self.fileName + ' RTSP/1.0\r\n' \
			          + 'CSeq: ' + str(self.rtspSeq) + '\r\n' \
			          + 'Session: ' + str(self.sessionId) + '\r\n\r\n'
			
			# Keep track of the sent request.
			self.requestSent = self.TEARDOWN
		
		# Describe request
		elif requestCode == self.DESCRIBE:
			# Update RTSP sequence number.
			self.rtspSeq += 1
			
			# Write the RTSP request to be sent.
			request = 'DESCRIBE ' + self.fileName + ' RTSP/1.0\r\n' \
			          + 'CSeq: ' + str(self.rtspSeq) + '\r\n' \
			          + 'Session: ' + str(self.sessionId) + '\r\n\r\n'
			
			# Keep track of the sent request.
			self.requestSent = self.DESCRIBE
		else:
			return
		
		# Send the RTSP request using rtspSocket.
		self.rtspSocket.send(request.encode())
		
		print('\nData sent:\n' + request)
	
	def recvRtspReply(self):
		"""Receive RTSP reply from the server."""
		while True:
			reply = self.rtspSocket.recv(1024)
			
			if reply: 
				self.parseRtspReply(reply.decode("utf-8"))
			
			# Close the RTSP socket upon requesting Teardown
			if self.requestSent == self.TEARDOWN:
				self.rtspSocket.shutdown(socket.SHUT_RDWR)
				self.rtspSocket.close()
				break
	
	def parseRtspReply(self, data):
		"""Parse the RTSP reply from the server."""
		lines = data.split('\n')
		seqNum = int(lines[1].split(' ')[1])
		
		# Process only if the server reply's sequence number is the same as the request's
		if seqNum == self.rtspSeq:
			session = int(lines[2].split(' ')[1])
			# New RTSP session ID
			if self.sessionId == 0:
				self.sessionId = session
			
			# Process only if the session ID is the same
			if self.sessionId == session:
				if int(lines[0].split(' ')[1]) == 200: 
					if self.requestSent == self.SETUP:
						# Update RTSP state.
						self.state = self.READY
						
						# Open RTP port.
						self.openRtpPort() 
					elif self.requestSent == self.PLAY:
						self.state = self.PLAYING
					elif self.requestSent == self.PAUSE:
						self.state = self.READY
						
						# The play thread exits. A new thread is created on resume.
						self.playEvent.set()
					elif self.requestSent == self.TEARDOWN:
						self.state = self.INIT
						
						# Flag the teardownAcked to close the socket.
						self.teardownAcked = 1 
					elif self.requestSent == self.DESCRIBE:
						# Parse SDP body from the response
						self.parseDescribeResponse(data)
	
	def openRtpPort(self):
		"""Open RTP socket binded to a specified port."""
		if self.mode == 'HD':
			# 3.3: TCP mode - create TCP server socket for RTP data
			self.rtpServerSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
			self.rtpServerSocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
			try:
				self.rtpServerSocket.bind(('', self.rtpPort))
				self.rtpServerSocket.listen(1)
				print(f"[TCP] Listening for RTP data on port {self.rtpPort}")
			except:
				tkinter.messagebox.showwarning('Unable to Bind', 'Unable to bind TCP PORT=%d' % self.rtpPort)
		else:
			# UDP mode (original behavior)
			self.rtpSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
			self.rtpSocket.settimeout(0.5)
			try:
				self.rtpSocket.bind(('', self.rtpPort))
			except:
				tkinter.messagebox.showwarning('Unable to Bind', 'Unable to bind PORT=%d' %self.rtpPort)

	def handler(self):
		"""Handler on explicitly closing the GUI window."""
		self.pauseMovie()
		if tkinter.messagebox.askokcancel("Quit?", "Are you sure you want to quit?"):
			self.exitClient()
		else: # When the user presses cancel, resume playing.
			self.playMovie()
	
	def parseDescribeResponse(self, data):
		"""Parse DESCRIBE response and display stream info."""
		try:
			# Extract SDP body (after the blank line)
			parts = data.split('\n\n', 1)
			if len(parts) > 1:
				sdpBody = parts[1]
			else:
				sdpBody = data
			
			# Parse SDP attributes
			info = []
			for line in sdpBody.strip().split('\n'):
				line = line.strip()
				if line.startswith('s='):
					info.append(f"Stream: {line[2:]}")
				elif line.startswith('i='):
					info.append(f"Info: {line[2:]}")
				elif line.startswith('m='):
					info.append(f"Media: {line[2:]}")
				elif line.startswith('a=mimetype:'):
					info.append(f"Type: {line[11:]}")
				elif line.startswith('a=filesize:'):
					size = int(line[11:])
					if size > 1024 * 1024:
						info.append(f"Size: {size / (1024*1024):.1f} MB")
					elif size > 1024:
						info.append(f"Size: {size / 1024:.1f} KB")
					else:
						info.append(f"Size: {size} bytes")
				elif line.startswith('a=transport:'):
					info.append(f"Transport: {line[12:]}")
			
			infoText = '\n'.join(info) if info else sdpBody
			tkinter.messagebox.showinfo("Stream Description", infoText)
			print(f"[DESCRIBE] {infoText}")
		except Exception as e:
			print(f"[DESCRIBE] Error parsing response: {e}")
