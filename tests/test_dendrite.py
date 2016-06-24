import unittest
import hbmqtt
import asyncio
import json

from origin.neuron import AsyncDendrite

broker_config = {
    'listeners': {
        'default': {
            'type': 'tcp',
            'bind': '127.0.0.1:18883',
            'max_connections': 10
        },
    },
    'sys_interval': 0,
    'auth': {
        'allow-anonymous': True,
    }
}

def run(coro):
    ''' helper function to run coroutines in asyncio loop'''
    return asyncio.get_event_loop().run_until_complete(coro)

class DendriteTest(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

        self.dendrite = AsyncDendrite(loop=self.loop)

        self.client = hbmqtt.client.MQTTClient()
        run(self.client.connect('mqtt://localhost:1883/'))


    def tearDown(self):
        run(self.client.disconnect())

        self.dendrite.finish()
        self.dendrite.run()
    
        self.loop.close()


    
    def test_add_task_sync(self):
        received_args=[]
        def task(*args):
            for arg in args:
                received_args.append(arg)
        
        self.dendrite.add_task(task, 'test', 'test2')
        
        self.dendrite.run()
        
        self.assertEqual(received_args, ['test', 'test2'])
        

    def test_publish(self):
        topic1 = 'test/topic1'
        topic2 = 'test/topic2'
        msg1 = dict(test='OK')
        run(self.client.subscribe( [
                    (topic1, hbmqtt.client.QOS_1),
                    (topic2, hbmqtt.client.QOS_1)
                ] ))
        
        self.dendrite.publish(topic1, msg1)
        self.dendrite.run()
        
        msg = run(self.client.deliver_message(1))
        self.assertEqual(json.loads(msg.data.decode()), msg1)
        self.assertEqual(msg.topic, topic1)
        
        msg2=dict(test=dict(OK='ok'), OK='ok')
        
        self.dendrite.publish(topic2, msg1)
        self.dendrite.publish(topic2, msg2)
        self.dendrite.publish(topic1, msg2)
        self.dendrite.run()

        msg = run(self.client.deliver_message(1))
        self.assertEqual(json.loads(msg.data.decode()), msg1)
        self.assertEqual(msg.topic, topic2)

        msg = run(self.client.deliver_message(1))
        self.assertEqual(json.loads(msg.data.decode()), msg2)
        self.assertEqual(msg.topic, topic2)

        msg = run(self.client.deliver_message(1))
        self.assertEqual(json.loads(msg.data.decode()), msg2)
        self.assertEqual(msg.topic, topic1)
        
        run(self.client.unsubscribe([topic1, topic2]))


    def test_subscribe_corofn(self):
        results = []
        async def get_msg(msg, topic):
            results.append({ 'msg': msg, 'topic': topic})
            self.dendrite.unsubscribe(topic)
        
        
        topic1 = 'test/topic1'
        msg1 = dict(test='OK', msg=1)

        
        self.dendrite.subscribe(topic1, get_msg)
        
        
        self.dendrite.add_task(self.client.publish(topic1, json.dumps(msg1).encode()))
        
        self.dendrite.run()
        
        self.assertEqual(results, [{'msg': msg1, 'topic': topic1}])
        
        results.pop()
        
    def test_subscribe_syncfn(self):
        results = []
        def get_msg(msg, topic):
            results.append({ 'msg': msg, 'topic': topic})
            self.dendrite.unsubscribe(topic)
        
        
        topic1 = 'test/topic1'
        msg1 = dict(test='OK', msg=1)

        
        self.dendrite.subscribe(topic1, get_msg)
        
        
        self.dendrite.add_task(self.client.publish(topic1, json.dumps(msg1).encode()))
        
        self.dendrite.run()
        
        self.assertEqual(results, [{'msg': msg1, 'topic': topic1}])
        
        results.pop()
        
    def test_subscribe_corofn_1arg(self):
        results = []
        topic1 = 'test/topic1'
        msg1 = dict(test='OK', msg=1)

        async def get_msg(msg):
            results.append({ 'msg': msg})
            self.dendrite.unsubscribe(topic1) # stop loop
        
        self.dendrite.subscribe(topic1, get_msg)
        
        
        self.dendrite.add_task(self.client.publish(topic1, json.dumps(msg1).encode()))
        
        self.dendrite.run()
        
        self.assertEqual(results, [{'msg': msg1}])
        
        results.pop()
        
    def test_subscribe_syncfn_1arg(self):
        results = []
        topic1 = 'test/topic1'
        msg1 = dict(test='OK', msg=1)

        def get_msg(msg):
            results.append({ 'msg': msg})
            self.dendrite.unsubscribe(topic1)
        
        
        self.dendrite.subscribe(topic1, get_msg)
        
        
        self.dendrite.add_task(self.client.publish(topic1, json.dumps(msg1).encode()))
        
        self.dendrite.run()
        
        self.assertEqual(results, [{'msg': msg1}])
        
        results.pop()


    def test_add_task_corofn(self):
        received_args=[]
        async def coro(*args):
            for arg in args:
                received_args.append(arg)
        
        self.dendrite.add_task(coro, 'test')
        
        self.dendrite.run()
        
        self.assertEqual(received_args, ['test'])
        
        
    def test_add_task_coro(self):
        received_args=[]
        async def coro(*args):
            for arg in args:
                received_args.append(arg)
        
        self.dendrite.add_task(coro('test'), 'ignored')
        
        self.dendrite.run()
        
        self.assertEqual(received_args, ['test'])
        
    def test_add_task_syncfn(self):
        received_args=[]
        def fn(*args):
            for arg in args:
                received_args.append(arg)
        
        self.dendrite.add_task(fn, 'test')
        
        self.dendrite.run()
        
        self.assertEqual(received_args, ['test'])
        
    def test_add_task_corofn_delay(self):
        import datetime
        
        result={}
        async def fn(*args):
            result['time'] = datetime.datetime.now()
        
        started = datetime.datetime.now()
        self.dendrite.add_task(fn, 'test', delay=2)
        
        self.dendrite.run()
        
        self.assertGreaterEqual((started - result['time']).seconds, 2)

    def test_add_task_coro_delay(self):
        import datetime
        
        result={}
        async def fn(*args):
            result['time'] = datetime.datetime.now()
        
        started = datetime.datetime.now()
        self.dendrite.add_task(fn('test'), delay=2)
        
        self.dendrite.run()
        
        self.assertGreaterEqual((started - result['time']).seconds, 2)
                

    def test_add_task_syncfn_delay(self):
        import datetime
        
        result={}
        def fn(*args):
            result['time'] = datetime.datetime.now()
        
        started = datetime.datetime.now()
        self.dendrite.add_task(fn, 'test', delay=2)
        
        self.dendrite.run()
        
        self.assertGreaterEqual((started - result['time']).seconds, 2)
                














        
        