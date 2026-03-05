from random import randint
import sys, traceback, threading, socket

from VideoStream import VideoStream
from RtpPacket import RtpPacket

class ServerWorker:
	SETUP = 'SETUP'
	PLAY = 'PLAY'
	PAUSE = 'PAUSE'
	TEARDOWN = 'TEARDOWN'
	
	INIT = 0
	READY = 1
	PLAYING = 2
	state = INIT

	OK_200 = 0
	FILE_NOT_FOUND_404 = 1
	CON_ERR_500 = 2
	
	clientInfo = {}
	seqNum = 0  # Global sequence number that increments for each RTP packet
	
	def __init__(self, clientInfo):
		self.clientInfo = clientInfo
		self.seqNum = 0  # Reset sequence number for each client
		
	def run(self):
		threading.Thread(target=self.recvRtspRequest).start()
	
	def recvRtspRequest(self):
		"""Receive RTSP request from the client."""
		connSocket = self.clientInfo['rtspSocket'][0]
		while True:            
			data = connSocket.recv(256)
			if data:
				print("Data received:\n" + data.decode("utf-8"))
				self.processRtspRequest(data.decode("utf-8"))
	
	def processRtspRequest(self, data):
		"""Process RTSP request sent from the client."""
		# Get the request type
		request = data.split('\n')
		line1 = request[0].split(' ')
		requestType = line1[0]
		
		# Get the media file name
		filename = line1[1]
		
		# Get the RTSP sequence number 
		seq = request[1].split(' ')
		
		# Process SETUP request
		if requestType == self.SETUP:
			if self.state == self.INIT:
				# Update state
				print("processing SETUP\n")
				
				try:
					self.clientInfo['videoStream'] = VideoStream(filename)
					self.state = self.READY
				except IOError:
					self.replyRtsp(self.FILE_NOT_FOUND_404, seq[1])
				
				# Generate a randomized RTSP session ID
				self.clientInfo['session'] = randint(100000, 999999)
				
				# Send RTSP reply
				self.replyRtsp(self.OK_200, seq[1])
				
				# Parse transport line: "Transport: RTP/UDP; client_port= 25000" or "Transport: RTP/TCP; client_port= 25000"
				transportLine = request[2]
				
				# Check if TCP or UDP transport
				if 'TCP' in transportLine.upper():
					self.clientInfo['transport'] = 'TCP'
				else:
					self.clientInfo['transport'] = 'UDP'
				
				# Get the RTP port from the last line
				self.clientInfo['rtpPort'] = transportLine.split(' ')[3]
				
				print(f"Transport: {self.clientInfo['transport']}, Port: {self.clientInfo['rtpPort']}")
		
		# Process PLAY request 		
		elif requestType == self.PLAY:
			if self.state == self.READY:
				print("processing PLAY\n")
				self.state = self.PLAYING
				
				address = self.clientInfo['rtspSocket'][1][0]
				port = int(self.clientInfo['rtpPort'])
				
				# Create socket based on transport type
				if self.clientInfo.get('transport') == 'TCP':
					# TCP mode for HD streaming
					self.clientInfo["rtpSocket"] = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
					self.clientInfo["rtpSocket"].setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
					
					# Set TCP buffer size for HD streaming
					self.clientInfo["rtpSocket"].setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 65536)
					
					try:
						# Connect to client's TCP port
						self.clientInfo["rtpSocket"].connect((address, port))
						print(f"TCP connection established to {address}:{port}")
					except Exception as e:
						print(f"TCP connection failed: {e}")
						self.state = self.READY
						return
				else:
					# UDP mode (default)
					self.clientInfo["rtpSocket"] = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
				
				self.replyRtsp(self.OK_200, seq[1])
				
				# Create a new thread and start sending RTP packets
				self.clientInfo['event'] = threading.Event()
				self.clientInfo['worker']= threading.Thread(target=self.sendRtp) 
				self.clientInfo['worker'].start()
		
		# Process PAUSE request
		elif requestType == self.PAUSE:
			if self.state == self.PLAYING:
				print("processing PAUSE\n")
				self.state = self.READY
				
				self.clientInfo['event'].set()
			
				self.replyRtsp(self.OK_200, seq[1])
		
		# Process TEARDOWN request
		elif requestType == self.TEARDOWN:
			print("processing TEARDOWN\n")

			# Stop the streaming thread
			if 'event' in self.clientInfo:
				self.clientInfo['event'].set()
			
			self.replyRtsp(self.OK_200, seq[1])
			
			# Close the RTP socket
			if 'rtpSocket' in self.clientInfo:
				self.clientInfo['rtpSocket'].close()
			
			# Reset state and session
			self.state = self.INIT
			self.clientInfo['session'] = 0
			self.seqNum = 0
			
	# Maximum payload size for RTP packet (avoid IP fragmentation)
	MAX_RTP_PAYLOAD_SIZE = 1400
	# For TCP HD streaming, we can use larger payload
	MAX_TCP_PAYLOAD_SIZE = 65000
	
	def sendRtp(self):
		"""Send RTP packets over UDP or TCP."""
		while True:
			self.clientInfo['event'].wait(0.05) 
			
			# Stop sending if request is PAUSE or TEARDOWN
			if self.clientInfo['event'].isSet(): 
				break 
				
			data = self.clientInfo['videoStream'].nextFrame()
			if data: 
				frameNumber = self.clientInfo['videoStream'].frameNbr()
				# Use frameNumber as timestamp (same for all fragments of a frame)
				timestamp = frameNumber * 90  # 90kHz clock typical for video
				
				try:
					address = self.clientInfo['rtspSocket'][1][0]
					port = int(self.clientInfo['rtpPort'])
					
					# Check transport type
					isTcp = self.clientInfo.get('transport') == 'TCP'
					
					if isTcp:
						# TCP mode for HD streaming - send entire frame
						# TCP handles fragmentation at transport layer, so we can send larger packets
						self.seqNum += 1
						packet = self.makeRtp(data, self.seqNum, marker=1, timestamp=timestamp)
						
						# Prefix packet with 4-byte length header for TCP framing
						packetLen = len(packet)
						lengthHeader = packetLen.to_bytes(4, byteorder='big')
						
						try:
							self.clientInfo['rtpSocket'].sendall(lengthHeader + packet)
						except (BrokenPipeError, ConnectionResetError):
							print("TCP connection lost")
							break
					else:
						# UDP mode - fragment if necessary
						if len(data) > self.MAX_RTP_PAYLOAD_SIZE:
							# Calculate number of fragments needed
							numFragments = (len(data) + self.MAX_RTP_PAYLOAD_SIZE - 1) // self.MAX_RTP_PAYLOAD_SIZE
							
							for i in range(numFragments):
								start = i * self.MAX_RTP_PAYLOAD_SIZE
								end = min(start + self.MAX_RTP_PAYLOAD_SIZE, len(data))
								fragment = data[start:end]
								
								# Use marker bit to indicate last fragment
								isLastFragment = (i == numFragments - 1)
								
								# Increment sequence number for each packet (continuous)
								self.seqNum += 1
								
								packet = self.makeRtp(fragment, self.seqNum, marker=1 if isLastFragment else 0, timestamp=timestamp)
								self.clientInfo['rtpSocket'].sendto(packet, (address, port))
						else:
							# No fragmentation needed, send as single packet with marker=1
							self.seqNum += 1
							self.clientInfo['rtpSocket'].sendto(self.makeRtp(data, self.seqNum, marker=1, timestamp=timestamp), (address, port))
				except Exception as e:
					print(f"Connection Error: {e}")
					#print('-'*60)
					#traceback.print_exc(file=sys.stdout)
					#print('-'*60)

	def makeRtp(self, payload, seqNum, marker=0, timestamp=None):
		"""RTP-packetize the video data."""
		version = 2
		padding = 0
		extension = 0
		cc = 0
		pt = 26 # MJPEG type
		ssrc = 0 
		
		rtpPacket = RtpPacket()
		
		rtpPacket.encode(version, padding, extension, cc, seqNum, marker, pt, ssrc, payload, timestamp)
		
		return rtpPacket.getPacket()
		
	def replyRtsp(self, code, seq):
		"""Send RTSP reply to the client."""
		if code == self.OK_200:
			#print("200 OK")
			reply = 'RTSP/1.0 200 OK\nCSeq: ' + seq + '\nSession: ' + str(self.clientInfo['session'])
			connSocket = self.clientInfo['rtspSocket'][0]
			connSocket.send(reply.encode())
		
		# Error messages
		elif code == self.FILE_NOT_FOUND_404:
			print("404 NOT FOUND")
		elif code == self.CON_ERR_500:
			print("500 CONNECTION ERROR")
