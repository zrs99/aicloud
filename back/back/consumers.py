from channels.generic.websocket import AsyncWebsocketConsumer
import json

class ProgressConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.task_id = self.scope['url_route']['kwargs']['task_id']
        self.group_name = f'progress_{self.task_id}'

        # 加入进度组
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )

        await self.accept()
        print("WebSocket connected")

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.group_name,
            self.channel_name
        )

        print("WebSocket disconnected")

    async def receive(self, text_data):
        print("receive")
        try:
            if text_data:
                print(text_data)
                # text_data_json = json.loads(text_data)  # 尝试解析 JSON
                # message = text_data_json.get('message')  # 获取具体字段

                # 处理业务逻辑...

                await self.send(text_data=json.dumps({
                    'response': 'Message received',
                    'original': 'Hello'
                }))
                # await self.send(text_data=json.dumps({
                #     'response': 'Message received',
                #     'original': '你好'
                # }))

        except json.JSONDecodeError:
            # 非 JSON 数据时的处理
            await self.send(text_data=json.dumps({
                'error': 'Invalid JSON format',
                'received_data': str(text_data)  # 打印原始数据用于调试
            }))

    async def progress_update(self, event):
        # 发送进度到客户端
        await self.send(text_data=json.dumps({
            'progress': event['progress']
        }))
