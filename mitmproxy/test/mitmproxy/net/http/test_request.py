from unittest import mock
import pytest

from mitmproxy.net.http import Headers, Request
from mitmproxy.test.tutils import treq
from .test_message import _test_decoded_attr, _test_passthrough_attr


class TestRequestData:
    def test_init(self):
        with pytest.raises(UnicodeEncodeError):
            treq(method="fööbär")
        with pytest.raises(UnicodeEncodeError):
            treq(scheme="fööbär")
        assert treq(host="fööbär").host == "fööbär"
        with pytest.raises(UnicodeEncodeError):
            treq(path="/fööbär")
        with pytest.raises(UnicodeEncodeError):
            treq(http_version="föö/bä.r")
        with pytest.raises(ValueError):
            treq(headers="foobar")
        with pytest.raises(ValueError):
            treq(content="foobar")
        with pytest.raises(ValueError):
            treq(trailers="foobar")

        assert isinstance(treq(headers=()).headers, Headers)
        assert isinstance(treq(trailers=()).trailers, Headers)


class TestRequestCore:
    """
    Tests for addons and the attributes that are directly proxied from the data structure
    """

    def test_repr(self):
        request = treq()
        assert repr(request) == "Request(GET address:22/path)"
        request.host = None
        assert repr(request) == "Request(GET /path)"

    def test_init_conv(self):
        assert Request(
            b"example.com",
            80,
            "GET",
            "http",
            "example.com",
            "/",
            "HTTP/1.1",
            (),
            None,
            (),
            0,
            0,
        )  # type: ignore

    def test_make(self):
        r = Request.make("GET", "https://example.com/")
        assert r.method == "GET"
        assert r.scheme == "https"
        assert r.host == "example.com"
        assert r.port == 443
        assert r.path == "/"

        r = Request.make("GET", "https://example.com/", "content", {"Foo": "bar"})
        assert r.content == b"content"
        assert r.headers["content-length"] == "7"
        assert r.headers["Foo"] == "bar"

        Request.make("GET", "https://example.com/", content=b"content")
        with pytest.raises(TypeError):
            Request.make("GET", "https://example.com/", content=42)

        r = Request.make("GET", "https://example.com/", headers=[(b"foo", b"bar")])
        assert r.headers["foo"] == "bar"

        r = Request.make("GET", "https://example.com/", headers=({"foo": "baz"}))
        assert r.headers["foo"] == "baz"

        r = Request.make("GET", "https://example.com/", headers=Headers(foo="qux"))
        assert r.headers["foo"] == "qux"

        with pytest.raises(TypeError):
            Request.make("GET", "https://example.com/", headers=42)

    def test_first_line_format(self):
        assert treq(method=b"CONNECT").first_line_format == "authority"
        assert treq(authority=b"example.com").first_line_format == "absolute"
        assert treq(authority=b"").first_line_format == "relative"

    def test_method(self):
        _test_decoded_attr(treq(), "method")

    def test_scheme(self):
        _test_decoded_attr(treq(), "scheme")

    def test_port(self):
        _test_passthrough_attr(treq(), "port")

    def test_path(self):
        _test_decoded_attr(treq(), "path")

    def test_authority(self):
        request = treq()
        assert request.authority == request.data.authority.decode("idna")

        # Test IDNA encoding
        # Set str, get raw bytes
        request.authority = "ídna.example"
        assert request.data.authority == b"xn--dna-qma.example"
        # Set raw bytes, get decoded
        request.data.authority = b"xn--idn-gla.example"
        assert request.authority == "idná.example"
        # Set bytes, get raw bytes
        request.authority = b"xn--dn-qia9b.example"
        assert request.data.authority == b"xn--dn-qia9b.example"
        # IDNA encoding is not bijective
        request.authority = "fußball"
        assert request.authority == "fussball"

        # Don't fail on garbage
        request.data.authority = b"foo\xFF\x00bar"
        assert request.authority.startswith("foo")
        assert request.authority.endswith("bar")
        # foo.bar = foo.bar should not cause any side effects.
        d = request.authority
        request.authority = d
        assert request.data.authority == b"foo\xFF\x00bar"

    def test_host_update_also_updates_header(self):
        request = treq()
        assert "host" not in request.headers
        request.host = "example.com"
        assert "host" not in request.headers

        request.headers["Host"] = "foo"
        request.authority = "foo"
        request.host = "example.org"
        assert request.headers["Host"] == "example.org"
        assert request.authority == "example.org:22"

    def test_get_host_header(self):
        no_hdr = treq()
        assert no_hdr.host_header is None

        h1 = treq(
            headers=((b"host", b"header.example.com"),),
            authority=b"authority.example.com"
        )
        assert h1.host_header == "header.example.com"

        h2 = h1.copy()
        h2.http_version = "HTTP/2.0"
        assert h2.host_header == "authority.example.com"

        h2_host_only = h2.copy()
        h2_host_only.authority = ""
        assert h2_host_only.host_header == "header.example.com"

    def test_modify_host_header(self):
        h1 = treq()
        assert "host" not in h1.headers

        h1.host_header = "example.com"
        assert h1.headers["Host"] == "example.com"
        assert not h1.authority

        h1.host_header = None
        assert "host" not in h1.headers
        assert not h1.authority

        h2 = treq(http_version=b"HTTP/2.0")
        h2.host_header = "example.org"
        assert "host" not in h2.headers
        assert h2.authority == "example.org"

        h2.headers["Host"] = "example.org"
        h2.host_header = "foo.example.com"
        assert h2.headers["Host"] == "foo.example.com"
        assert h2.authority == "foo.example.com"

        h2.host_header = None
        assert "host" not in h2.headers
        assert not h2.authority


class TestRequestUtils:
    """
    Tests for additional convenience methods.
    """

    def test_url(self):
        request = treq()
        assert request.url == "http://address:22/path"

        request.url = "https://otheraddress:42/foo"
        assert request.scheme == "https"
        assert request.host == "otheraddress"
        assert request.port == 42
        assert request.path == "/foo"

        with pytest.raises(ValueError):
            request.url = "not-a-url"

    def test_url_options(self):
        request = treq(method=b"OPTIONS", path=b"*")
        assert request.url == "http://address:22"

    def test_url_authority(self):
        request = treq(method=b"CONNECT")
        assert request.url == "address:22"

    def test_pretty_host(self):
        request = treq()
        # Without host header
        assert request.pretty_host == "address"
        assert request.host == "address"
        # Same port as self.port (22)
        request.headers["host"] = "other:22"
        assert request.pretty_host == "other"

        # Invalid IDNA
        request.headers["host"] = ".disqus.com"
        assert request.pretty_host == ".disqus.com"

    def test_pretty_url(self):
        request = treq()
        # Without host header
        assert request.url == "http://address:22/path"
        assert request.pretty_url == "http://address:22/path"

        request.headers["host"] = "other:22"
        assert request.pretty_url == "http://other:22/path"

        request = treq(method=b"CONNECT", authority=b"example:44")
        assert request.pretty_url == "example:44"

    def test_pretty_url_options(self):
        request = treq(method=b"OPTIONS", path=b"*")
        assert request.pretty_url == "http://address:22"

    def test_pretty_url_authority(self):
        request = treq(method=b"CONNECT", authority="address:22")
        assert request.pretty_url == "address:22"

    def test_get_query(self):
        request = treq()
        assert not request.query

        request.url = "http://localhost:80/foo?bar=42"
        assert dict(request.query) == {"bar": "42"}

    def test_set_query(self):
        request = treq()
        assert not request.query
        request.query["foo"] = "bar"
        assert request.query["foo"] == "bar"
        assert request.path == "/path?foo=bar"
        request.query = [('foo', 'bar')]
        assert request.query["foo"] == "bar"
        assert request.path == "/path?foo=bar"

    def test_get_cookies_none(self):
        request = treq()
        request.headers = Headers()
        assert not request.cookies

    def test_get_cookies_single(self):
        request = treq()
        request.headers = Headers(cookie="cookiename=cookievalue")
        assert len(request.cookies) == 1
        assert request.cookies['cookiename'] == 'cookievalue'

    def test_get_cookies_double(self):
        request = treq()
        request.headers = Headers(cookie="cookiename=cookievalue;othercookiename=othercookievalue")
        result = request.cookies
        assert len(result) == 2
        assert result['cookiename'] == 'cookievalue'
        assert result['othercookiename'] == 'othercookievalue'

    def test_get_cookies_withequalsign(self):
        request = treq()
        request.headers = Headers(cookie="cookiename=coo=kievalue;othercookiename=othercookievalue")
        result = request.cookies
        assert len(result) == 2
        assert result['cookiename'] == 'coo=kievalue'
        assert result['othercookiename'] == 'othercookievalue'

    def test_set_cookies(self):
        request = treq()
        request.headers = Headers(cookie="cookiename=cookievalue")
        result = request.cookies
        result["cookiename"] = "foo"
        assert request.cookies["cookiename"] == "foo"
        request.cookies = [["one", "uno"], ["two", "due"]]
        assert request.cookies["one"] == "uno"
        assert request.cookies["two"] == "due"

    def test_get_path_components(self):
        request = treq(path=b"/foo/bar")
        assert request.path_components == ("foo", "bar")

    def test_set_path_components(self):
        request = treq()
        request.path_components = ["foo", "baz"]
        assert request.path == "/foo/baz"

        request.path_components = []
        assert request.path == "/"

        request.path_components = ["foo", "baz"]
        request.query["hello"] = "hello"
        assert request.path_components == ("foo", "baz")

        request.path_components = ["abc"]
        assert request.path == "/abc?hello=hello"

    def test_anticache(self):
        request = treq()
        request.headers["If-Modified-Since"] = "foo"
        request.headers["If-None-Match"] = "bar"
        request.anticache()
        assert "If-Modified-Since" not in request.headers
        assert "If-None-Match" not in request.headers

    def test_anticomp(self):
        request = treq()
        request.headers["Accept-Encoding"] = "foobar"
        request.anticomp()
        assert request.headers["Accept-Encoding"] == "identity"

    def test_constrain_encoding(self):
        request = treq()

        h = request.headers.copy()
        request.constrain_encoding()  # no-op if there is no accept_encoding header.
        assert request.headers == h

        request.headers["Accept-Encoding"] = "identity, gzip, foo"
        request.constrain_encoding()
        assert "foo" not in request.headers["Accept-Encoding"]
        assert "gzip" in request.headers["Accept-Encoding"]

    def test_get_urlencoded_form(self):
        request = treq(content=b"foobar=baz")
        assert not request.urlencoded_form

        request.headers["Content-Type"] = "application/x-www-form-urlencoded"
        assert list(request.urlencoded_form.items()) == [("foobar", "baz")]
        request.raw_content = b"\xFF"
        assert len(request.urlencoded_form) == 1

    def test_set_urlencoded_form(self):
        request = treq(content=b"\xec\xed")
        request.urlencoded_form = [('foo', 'bar'), ('rab', 'oof')]
        assert request.headers["Content-Type"] == "application/x-www-form-urlencoded"
        assert request.content

    def test_get_multipart_form(self):
        request = treq(content=b"foobar")
        assert not request.multipart_form

        request.headers["Content-Type"] = "multipart/form-data"
        assert list(request.multipart_form.items()) == []

        with mock.patch('mitmproxy.net.http.multipart.decode') as m:
            m.side_effect = ValueError
            assert list(request.multipart_form.items()) == []

    def test_set_multipart_form(self):
        request = treq()
        request.multipart_form = [("file", "shell.jpg"), ("file_size", "1000")]
        assert request.headers["Content-Type"] == 'multipart/form-data'
        assert request.content is None
