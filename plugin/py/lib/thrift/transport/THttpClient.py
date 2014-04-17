#
# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements. See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership. The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License. You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied. See the License for the
# specific language governing permissions and limitations
# under the License.
#

from TTransport import *
from cStringIO import StringIO

import urlparse
import httplib
import warnings
import socket
import os
import platform

class THttpClient(TTransportBase):

  """Http implementation of TTransport base."""

  def __init__(self, uri_or_host, port=None, path=None):
    """THttpClient supports two different types constructor parameters.

    THttpClient(host, port, path) - deprecated
    THttpClient(uri)

    Only the second supports https."""

    if port is not None:
      warnings.warn("Please use the THttpClient('http://host:port/path') syntax", DeprecationWarning, stacklevel=2)
      self.host = uri_or_host
      self.port = port
      assert path
      self.path = path
      self.scheme = 'http'
    else:
      parsed = urlparse.urlparse(uri_or_host)
      self.scheme = parsed.scheme
      assert self.scheme in ('http', 'https')
      if self.scheme == 'http':
        self.port = parsed.port or httplib.HTTP_PORT
      elif self.scheme == 'https':
        self.port = parsed.port or httplib.HTTPS_PORT
      self.host = parsed.hostname
      self.path = parsed.path
      if parsed.query:
        self.path += '?%s' % parsed.query
    self.__wbuf = StringIO()
    self.__http = None
    self.__timeout = None
    self.proxy_host = None
    self.proxy_port = None
    if platform.system() is 'Windows':
      from _winreg import *
      import _winreg as winreg
      key = winreg.OpenKey(HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Internet Settings', 0, KEY_READ)
      if winreg.QueryValueEx(key, 'ProxyEnable')[0] is 1:
        proxy = winreg.QueryValueEx(key, "ProxyServer")[0]
        self.proxy_host = proxy.split(':')[0]
        self.proxy_port = proxy.split(':')[1]
      winreg.CloseKey(key)
    else:
      http_proxy = os.environ.get('http_proxy')
      if http_proxy is not None:
        parsed = urlparse.urlparse(http_proxy)
        self.proxy_host = parsed.hostname
        self.proxy_port = parsed.port

  def open(self):
    if self.scheme is 'http':
      if self.proxy_host is not None:
        self.__http = httplib.HTTP(self.proxy_host, str(self.proxy_port))
        self.__http._conn.set_tunnel(self.host, self.port)
      else:
        self.__http = httplib.HTTP(self.host, self.port)
    else:
      if self.proxy_host is not None:
        self.__http = httplib.HTTPS(self.proxy_host, str(self.proxy_port))
        self.__http._conn.set_tunnel(self.host, self.port)
      else:
        self.__http = httplib.HTTPS(self.host, self.port)

  def close(self):
    self.__http.close()
    self.__http = None

  def isOpen(self):
    return self.__http != None

  def setTimeout(self, ms):
    if not hasattr(socket, 'getdefaulttimeout'):
      raise NotImplementedError

    if ms is None:
      self.__timeout = None
    else:
      self.__timeout = ms/1000.0

  def read(self, sz):
    return self.__http.file.read(sz)

  def write(self, buf):
    self.__wbuf.write(buf)

  def __withTimeout(f):
    def _f(*args, **kwargs):
      orig_timeout = socket.getdefaulttimeout()
      socket.setdefaulttimeout(args[0].__timeout)
      result = f(*args, **kwargs)
      socket.setdefaulttimeout(orig_timeout)
      return result
    return _f

  def flush(self):
    if self.isOpen():
      self.close()
    self.open();

    # Pull data out of buffer
    data = self.__wbuf.getvalue()
    self.__wbuf = StringIO()

    # HTTP request
    self.__http.putrequest('POST', self.path)

    # Write headers
    self.__http.putheader('Host', self.host)
    self.__http.putheader('Content-Type', 'application/x-thrift')
    self.__http.putheader('Content-Length', str(len(data)))
    self.__http.endheaders()

    # Write payload
    self.__http.send(data)

    # Get reply to flush the request
    self.code, self.message, self.headers = self.__http.getreply()

  # Decorate if we know how to timeout
  if hasattr(socket, 'getdefaulttimeout'):
    flush = __withTimeout(flush)
