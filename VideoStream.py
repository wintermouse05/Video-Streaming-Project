class VideoStream:
	def __init__(self, filename):
		self.filename = filename
		try:
			self.file = open(filename, 'rb')
		except:
			raise IOError
		self.frameNum = 0
		self.isRawMjpeg = False
		self.frames = []
		
		# Auto-detect frame format
		# Read first bytes to determine format
		self.prefixLen = self._detectPrefixLen()
		
		# If raw MJPEG, pre-load frames into memory for fast access
		if self.isRawMjpeg:
			self.file.seek(0)
			data = self.file.read()
			pos = 0
			while pos < len(data) - 1:
				soi = data.find(b'\xff\xd8', pos)
				if soi == -1:
					break
				eoi = data.find(b'\xff\xd9', soi + 2)
				if eoi == -1:
					break
				self.frames.append(data[soi:eoi + 2])
				pos = eoi + 2
		
	def _detectPrefixLen(self):
		"""Detect whether the file uses 5/6 byte frame prefix, or is RAW MJPEG."""
		pos = self.file.tell()
		header = self.file.read(6)
		self.file.seek(pos)  # Reset position
		
		# Check for Raw MJPEG (starts with JPEG SOI marker FF D8)
		if len(header) >= 2 and header[:2] == b'\xff\xd8':
			self.isRawMjpeg = True
			return 0
		
		if len(header) < 5:
			return 5  # Default
		
		# Try 5-byte prefix first
		try:
			frameLen5 = int(header[:5])
			# Validate: read the frame and check if next prefix is also valid
			self.file.seek(pos + 5 + frameLen5)
			next_header = self.file.read(5)
			self.file.seek(pos)
			if len(next_header) >= 5:
				try:
					int(next_header[:5])
					return 5  # 5-byte prefix works
				except ValueError:
					pass
			elif len(next_header) == 0:
				return 5  # Only one frame, assume 5
		except ValueError:
			pass
		
		# Try 6-byte prefix
		try:
			frameLen6 = int(header[:6])
			self.file.seek(pos + 6 + frameLen6)
			next_header = self.file.read(6)
			self.file.seek(pos)
			if len(next_header) >= 6:
				try:
					int(next_header[:6])
					return 6
				except ValueError:
					pass
			elif len(next_header) == 0:
				return 6
		except ValueError:
			pass
		
		return 5  # Default fallback
	
	def nextFrame(self):
		"""Get next frame."""
		if self.isRawMjpeg:
			if self.frameNum < len(self.frames):
				frame = self.frames[self.frameNum]
				self.frameNum += 1
				return frame
			return b''
			
		data = self.file.read(self.prefixLen)  # Get the framelength from prefix
		if data: 
			framelength = int(data)
							
			# Read the current frame
			data = self.file.read(framelength)
			self.frameNum += 1
		return data
		
	def frameNbr(self):
		"""Get frame number."""
		return self.frameNum