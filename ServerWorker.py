from random import randint
import sys, traceback, threading, socket, struct

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
	
	def __init__(self, clientInfo):
		self.clientInfo = clientInfo
		
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
				
				# Parse transport line for mode and port
				transportLine = request[2]
				
				# 3.3: Detect transport mode (TCP or UDP)
				if 'RTP/TCP' in transportLine:
					self.clientInfo['transportMode'] = 'TCP'
					print("[SERVER] Transport mode: TCP (HD)")
				else:
					self.clientInfo['transportMode'] = 'UDP'
					print("[SERVER] Transport mode: UDP (SD)")
				
				# Extract client port (robust parsing)
				portStr = transportLine.split('client_port=')[1].strip().rstrip('\r\n')
				# Remove any non-digit characters
				self.clientInfo['rtpPort'] = ''.join(c for c in portStr if c.isdigit())
		
		# Process PLAY request 		
		elif requestType == self.PLAY:
			if self.state == self.READY:
				print("processing PLAY\n")
				self.state = self.PLAYING
				
				# 3.3: Create socket based on transport mode
				if self.clientInfo.get('transportMode') == 'TCP':
					# TCP mode: connect to client's TCP RTP port (reuse if exists)
					if 'rtpSocket' not in self.clientInfo or self.clientInfo['rtpSocket'] is None:
						self.clientInfo['rtpSocket'] = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
						address = self.clientInfo['rtspSocket'][1][0]
						port = int(self.clientInfo['rtpPort'])
						self.clientInfo['rtpSocket'].connect((address, port))
						print(f"[SERVER] TCP RTP connected to {address}:{port}")
				else:
					# UDP mode: create a new datagram socket
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

			self.clientInfo['event'].set()
			
			self.replyRtsp(self.OK_200, seq[1])
			
			# Close the RTP socket
			try:
				self.clientInfo['rtpSocket'].close()
			except:
				pass
			self.clientInfo['rtpSocket'] = None
			
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
				try:
					packet = self.makeRtp(data, frameNumber)
					
					# 3.3: Send via TCP or UDP based on transport mode
					if self.clientInfo.get('transportMode') == 'TCP':
						# TCP: send with 4-byte length prefix
						lengthPrefix = struct.pack('>I', len(packet))
						self.clientInfo['rtpSocket'].sendall(lengthPrefix + packet)
					else:
						# UDP: send as datagram
						address = self.clientInfo['rtspSocket'][1][0]
						port = int(self.clientInfo['rtpPort'])
						self.clientInfo['rtpSocket'].sendto(packet, (address, port))
				except:
					print("Connection Error")
					#print('-'*60)
					#traceback.print_exc(file=sys.stdout)
					#print('-'*60)

	def makeRtp(self, payload, frameNbr):
		"""RTP-packetize the video data."""
		version = 2
		padding = 0
		extension = 0
		cc = 0
		marker = 1  # 2.6: Mark as last (only) fragment of the frame
		pt = 26 # MJPEG type
		seqnum = frameNbr
		ssrc = 0 
		
		rtpPacket = RtpPacket()
		
		rtpPacket.encode(version, padding, extension, cc, seqnum, marker, pt, ssrc, payload)
		
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
