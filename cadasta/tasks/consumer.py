import logging

import boto3
from django.conf import settings
from django.db.models import F
from django.db.models.expressions import CombinedExpression, Value
from kombu.mixins import ConsumerMixin

from .models import BackgroundTask


logger = logging.getLogger(__name__)


class Worker(ConsumerMixin):

    def __init__(self, connection, queues):
        self.connection = connection
        self.queues = queues
        super(Worker, self).__init__()
        logger.info("Started worker %r for queues %r", self, self.queues)

    def get_consumers(self, Consumer, channel):
        return [Consumer(queues=self.queues,
                         accept=['pickle', 'json'],
                         callbacks=[self.process_task])]

    def process_task(self, body, message):
        logger.info('Processing message: %r', message)
        try:
            handler = self._detect_msg_type(message)
            return handler(body, message)
        except TypeError:
            logger.exception("Unknown message type: %r", message)
        except:
            logger.exception("Failed to process message: %r", message)
        finally:
            logger.info("ACKing message %r", message)
            if self.connection.as_uri().startswith('sqs://'):
                # HACK: Can't seem to get message.ack() to work for SQS
                # backend. Without this hack, messages will keep
                # re-appearing after the visibility_timeout expires.
                # See https://github.com/celery/kombu/issues/758
                return self._sqs_ack(message)
            return message.ack()

    def _sqs_ack(self, message):
        logger.debug("Manually ACKing SQS message %r", message)
        region = settings.CELERY_BROKER_TRANSPORT_OPTIONS['region']
        boto3.client('sqs', region).delete_message(
            QueueUrl=message.delivery_info['sqs_queue'],
            ReceiptHandle=message.delivery_info['sqs_message']['ReceiptHandle']
        )
        message._state = 'ACK'
        message.channel.qos.ack(message.delivery_tag)

    def _detect_msg_type(self, message):
        if 'task' in message.headers:
            return self._handle_task
        if 'result' in message.payload:
            return self._handle_result
        raise TypeError("Cannot detect message type")

    @staticmethod
    def _handle_task(body, message):
        logger.debug("Handling task message %r", body)
        args, kwargs, options = message.decode()
        task_id = message.headers['id']

        # Add default properties
        option_keys = ['eta', 'expires', 'retries', 'timelimit']
        message.properties.update(
            **{k: v for k, v in message.headers.items()
               if k in option_keys and v not in (None, [None, None])})

        # TODO: Add support for grouped tasks
        # TODO: Add support tasks gednerated by workers
        _, created = BackgroundTask.objects.get_or_create(
            id=task_id,
            defaults={
                'type': message.headers['task'],
                'input_args': args,
                'input_kwargs': kwargs,
                'options': message.properties,
                'parent_id': message.headers['parent_id'],
                'root_id': message.headers['root_id'],
            }
        )
        if created:
            logger.debug("Processed task: %r", message)
        else:
            logger.warn("Task already existed in db: %r", message)

    @staticmethod
    def _handle_result(body, message):
        logger.debug("Handling result message %r", body)
        result = message.payload
        logger.debug('Received message: %r', result)
        t_id = result['task_id']
        task_qs = BackgroundTask.objects.filter(id=t_id)

        if not task_qs.exists():
            return logger.error("No corresponding task found (%r)", t_id)

        status = result.get('status')
        if status:
            task_qs.update(status=status)

        result = result['result']
        if status in BackgroundTask.DONE_STATES:
            task_qs.update(output=result)
        else:
            if not isinstance(result, dict):
                msg = "Malformed result data, expecting a dict, got %s (%r)"
                return logger.error(msg, type(result), result)
            log = result.get('log')
            if log:
                task_qs.update(log=CombinedExpression(
                    F('log'), '||', Value([log])
                ))
