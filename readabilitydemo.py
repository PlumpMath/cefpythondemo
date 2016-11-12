import time
import sys
import urllib
import threading

from cefpython3 import cefpython

# This is injected into the loaded page.
READABILITY_JS = open('readability-js/readability.js').read()

settings = {
		"log_severity": cefpython.LOGSEVERITY_INFO, # LOGSEVERITY_VERBOSE
		#"log_file": GetApplicationPath("debug.log"), # Set to "" to disable.
		"release_dcheck_enabled": True, # Enable only when debugging.
		# This directories must be set on Linux
		#"locales_dir_path": cefpython.GetModuleDirectory()+"/locales",

		"resources_dir_path": cefpython.GetModuleDirectory() + '/Resources',
		"browser_subprocess_path": "%s/%s" % (cefpython.GetModuleDirectory(), "subprocess"),
		}

switches = {
		"locale_pak": cefpython.GetModuleDirectory() +"/Resources/en.lproj/locale.pak",
}

READABILITY_HEADER = """
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<link rel="stylesheet" type="text/css" href="readability-js/readability.css">
<title>Readability result</title>
</head>
<body>
"""

READABILITY_FOOTER = """
</body>
</html>
"""

def writeReadabilityResult(html):
	with open('readable.html', 'w') as h:
		h.write(READABILITY_HEADER)
		h.write(html)
		h.write(READABILITY_FOOTER)

class CustomResourceHandler:
	def __init__(self, clientHandler, request):
		self.clientHandler = clientHandler
		self.request = request
		print "Custom resource: ", request.GetUrl()
		#print "Post data ", request.GetPostData()
		postData = request.GetPostData()

		if 'html' in postData:
			html = urllib.unquote(postData['html'])
			writeReadabilityResult(postData['html'])

			# Work is done:
			self.clientHandler._requestQuit()
	
	def ProcessRequest(self, request, callback):
		# call callback.Continue() when headers are available -- which they are immediately...
		callback.Continue()
		return True

	def GetResponseHeaders(self, response, responseLengthOut, redirectUrlOut):
		print "GetResponseHeaders"
		response.SetStatus(200)
		response.SetStatusText("OK")
		response.SetMimeType("text/plain")
		response.SetHeaderMap({'Access-Control-Allow-Origin': '*'})
		responseLengthOut[0] = 0

	def ReadResponse(self, dataOut, bytesToRead, bytesReadOut, callback):
		print "ReadResponse"
		return False

	def CanGetCookie(self):
		return False

	def CanSetCookie(self):
		return False

	def Cancel(self):
		pass
	
class ClientHandler:
	"""A client handler is required for the browser to do built in callbacks back into the application."""

	def __init__(self, browser, finished_cv):
		self.browser = browser
		self.resourceHandlers = set()
		self.finished_cv = finished_cv
		self.okToQuit = False
		self.injectedReadability = False

	def OnPaint(self, browser, paintElementType, dirtyRects, buf, width, height):
		print "OnPaint"

	def GetViewRect(self, browser, rect):
		print "GetViewRect"
		rect.extend([0, 0, 1024, 768])
		return True

	def GetScreenPoint(self, browser, viewX, viewY, screenCoordinates):
		print("GetScreenPoint()")
		return False

	def OnLoadEnd(self, browser, frame, httpStatusCode):
		print "OnLoadEnd"
		#self.browser.GetMainFrame().ExecuteJavascript(CUSTOM_RESPONSE_JAVASCRIPT)
		if not self.injectedReadability:
			self.browser.GetMainFrame().ExecuteJavascript(READABILITY_JS)
			self.injectedReadability = True

	def OnLoadError(self, browser, frame, errorCode, errorText, failedURL):
		print("load error", browser, frame, errorCode, errorText, failedURL)

	def GetResourceHandler(self, browser, frame, request):
		# This code from https://github.com/cztomczak/cefpython/blob/master/src/linux/binaries_64bit/wxpython-response.py
		print "GetResourceHandler", request.GetUrl()
		if request.GetUrl().startswith('http://cef/'):
			# Custom URL scheme for storing data from JS
			handler = CustomResourceHandler(self, request)
			self.resourceHandlers.add(handler)
			return handler
		else:
			# Behave as normal for now.
			handler = None

		return handler

	def _requestQuit(self):
		self.okToQuit = True
		self.finished_cv.acquire()
		self.finished_cv.notify()
		self.finished_cv.release()

	def _customResourceHandlerFinished(self, resourceHandler):
		try:
			self.resourceHandlers.remove(resourceHandler)
		except KeyError:
			# eh
			print >>sys.stderr, "customResourceHandlerFinished: unknown resourceHandler ", resourceHandler

	def _extractorStateMachine(self):
		pass

MESSAGE_LOOP_CALL_FREQUENCY_SECS = 10.0/1000.0
def main():
	url = sys.argv[1]

	cefpython.Initialize(settings, switches)

	windowInfo = cefpython.WindowInfo()
	windowInfo.SetAsOffscreen(0)

	browserSettings = {
		# Remove same-origin policy.
		"web_security_disabled": False,
	}

	browser = cefpython.CreateBrowserSync(
			windowInfo, browserSettings,
			navigateUrl = url)
	browser.SendFocusEvent(True)

	finished_cv = threading.Condition()
	clientHandler = ClientHandler(browser, finished_cv)

	browser.SetClientHandler(clientHandler)

	finished_cv.acquire()
	# Run until browser terminates us. TODO: WDT if something goes wrong when parsing?
	while True:
		finished_cv.wait(MESSAGE_LOOP_CALL_FREQUENCY_SECS)
		if clientHandler.okToQuit:
			break
		else:
			cefpython.MessageLoopWork()

	# Delete all browser refererences to ensure cookies flushed to disk etc.
	del clientHandler.browser
	del browser

	cefpython.Shutdown()

if __name__ == '__main__':
	main()

