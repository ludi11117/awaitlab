import asyncio
import importlib.util
import unittest
from awaitlab import Session,operation
from awaitlab.asgi import LocalASGITrace
from awaitlab.trace import capture_context


class BridgeTests(unittest.IsolatedAsyncioTestCase):
    async def invoke(self,app,ticket,peer='127.0.0.1'):
        sent=[]
        async def receive():return {'type':'http.request','body':b'','more_body':False}
        async def send(message):sent.append(message)
        headers=[(b'x-awaitlab-ticket',ticket.encode())] if ticket else []
        await app({'type':'http','headers':headers,'client':(peer,123)},receive,send)
        return sent

    async def test_no_active_session_adds_no_ticket(self):
        bridge=LocalASGITrace()
        with bridge.headers() as headers:self.assertEqual(headers,{})
        self.assertEqual(bridge.pending_tickets,0)

    async def test_ordinary_request_does_not_inherit_incidental_experiment(self):
        bridge=LocalASGITrace();seen=[]
        @operation('work')
        async def work():seen.append('original')
        async def replacement():seen.append('replacement')
        async def app(scope,receive,send):
            self.assertIsNone(capture_context())
            await work()
        with Session(replacements={'work':replacement}) as session:
            await self.invoke(bridge.middleware(app),None)
            self.assertIs(capture_context().session,session)
        self.assertEqual(seen,['original'])
        self.assertEqual(session.replacement_calls,0)

    async def test_bridge_attaches_origin_request_and_parent_in_detached_task(self):
        bridge=LocalASGITrace();seen=[]
        @operation('server.work')
        async def work():
            seen.append(capture_context().request_id)
            await asyncio.sleep(0)
        async def app(scope,receive,send):
            await work();await send({'type':'http.response.start','status':200,'headers':[]})
            await send({'type':'http.response.body','body':b'ok'})
        wrapped=bridge.middleware(app)
        with Session() as session:
            async with session.request(1):
                with bridge.headers() as headers:
                    import contextvars
                    task=contextvars.Context().run(asyncio.create_task,self.invoke(wrapped,headers[bridge.header]))
                    await task
        self.assertEqual(seen,[1])
        records={r.id:r for r in session.records}
        child=next(r for r in records.values() if r.name=='server.work')
        server=records[child.parent];root=records[server.parent]
        self.assertEqual(server.name,'http.server');self.assertEqual(root.name,'request')
        self.assertNotEqual(child.task,root.task)
        self.assertEqual(bridge.pending_tickets,0)

    async def test_ticket_is_single_use_and_invalid_peer_cannot_attach(self):
        bridge=LocalASGITrace()
        async def app(scope,receive,send):await send({'type':'http.response.start','status':200,'headers':[]})
        wrapped=bridge.middleware(app)
        with Session():
            with bridge.headers() as headers:
                ticket=headers[bridge.header]
                denied=await self.invoke(wrapped,ticket,'203.0.113.2')
                self.assertEqual(denied[0]['status'],403)
                accepted=await self.invoke(wrapped,ticket)
                self.assertEqual(accepted[0]['status'],200)
                reused=await self.invoke(wrapped,ticket)
                self.assertEqual(reused[0]['status'],403)
        self.assertEqual(bridge.pending_tickets,0)

    async def test_context_and_unused_ticket_cleaned_after_failure(self):
        bridge=LocalASGITrace()
        async def bad(scope,receive,send):raise RuntimeError('expected')
        with Session() as session:
            async with session.request(0):
                original=capture_context()
                with bridge.headers() as headers:
                    with self.assertRaises(RuntimeError):await self.invoke(bridge.middleware(bad),headers[bridge.header])
                self.assertEqual(capture_context(),original)
                with bridge.headers():self.assertEqual(bridge.pending_tickets,1)
        self.assertEqual(bridge.pending_tickets,0)
        self.assertEqual(session.stats[('http.server','transport')]['failed'],1)


@unittest.skipUnless(all(importlib.util.find_spec(m) for m in ['fastapi','httpx','uvicorn']),
                     'Optional network integration dependencies not installed')
class TCPTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_tcp_traffic_preserves_interventions_and_outputs(self):
        from examples.fastapi_tcp import application
        from awaitlab import Arm,Experiment,Settings
        from awaitlab.scenarios import fast_pricing
        experiment=Experiment(application,[Arm('fast','replacement','pricing.quote',
            replacements={'pricing.quote':fast_pricing})],Settings(blocks=2,requests=4,warmup=1))
        report=await experiment.run()
        c=report['comparisons'][0]
        self.assertTrue(c['output_equivalence'])
        for pair in c['blocks']:
            self.assertEqual(pair['treatment']['replacement_calls'],4)
            self.assertEqual(next(o['count'] for o in pair['control']['operations'] if o['name']=='http.server'),4)


if __name__=='__main__':unittest.main()
