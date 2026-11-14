"""Explicit context bridging for loopback, single-process ASGI experiments."""
from contextlib import contextmanager
import ipaddress
import secrets
from .trace import capture_context,TraceContext


class LocalASGITrace:
    """Share this instance between the app middleware and its local load client.

    Each HTTP request carries a one-use random ticket, not serialized tracing data.
    This intentionally does not implement distributed/multi-worker propagation.
    """
    header='x-awaitlab-ticket'

    def __init__(self):
        self._tickets={}

    @property
    def pending_tickets(self):
        return len(self._tickets)

    @contextmanager
    def headers(self):
        context=capture_context()
        if context is None:
            yield {}
            return
        ticket=secrets.token_urlsafe(24)
        self._tickets[ticket]=context
        try:yield {self.header:ticket}
        finally:self._tickets.pop(ticket,None)

    def middleware(self,app):
        async def wrapped(scope,receive,send):
            if scope['type']!='http':
                return await app(scope,receive,send)
            tickets=[v for k,v in scope.get('headers',[]) if k.lower()==self.header.encode()]
            if not tickets:
                # A server started under an active Session may inherit that
                # context. Ordinary requests must never inherit its intervention.
                with TraceContext(None,None,None).attach():
                    return await app(scope,receive,send)
            peer=scope.get('client')
            try:local=peer is not None and ipaddress.ip_address(peer[0]).is_loopback
            except ValueError:local=False
            ticket=tickets[0].decode('ascii',errors='replace')
            context=self._tickets.pop(ticket,None) if local and len(tickets)==1 else None
            if context is None:
                await send({'type':'http.response.start','status':403,
                            'headers':[(b'content-type',b'application/json')]})
                return await send({'type':'http.response.body','body':b'{"error":"invalid local experiment ticket"}'})
            with context.attach():
                with context.session.span('http.server','transport'):
                    return await app(scope,receive,send)
        return wrapped
