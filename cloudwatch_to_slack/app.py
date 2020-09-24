import json
import logging
import os

from datetime import datetime
from urllib import parse
from urllib.error import URLError, HTTPError
from urllib.request import Request, urlopen

WEBHOOK_URL = os.environ['SLACK_WEBHOOK_URL']

LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)

LINK = 'https://console.aws.amazon.com/cloudwatch/home?region={}#s=Alarms&alarm={}'

COLORS = {
    'ALARM': '#A30200',
    'OK': '#2EB886',
    'INSUFFICIENT_DATA': '#DAA038'
}

OPERATORS = {
    'GreaterThanThreshold': '>',
    'GreaterThanOrEqualToThreshold': '>=',
    'LessThanThreshold': '<',
    'LessThanOrEqualToThreshold': '<='
}

UNKNOWN_COLOR = '#808080'
UNKNOWN_OPERATOR = 'unknown'


def lambda_handler(event, _context):
    LOGGER.info('Event received: \n%s', event)
    for single_event in event['Records']:
        sns_message = json.loads(single_event['Sns']['Message'])
        slack_message = prepare_slack_message(sns_message)
        if WEBHOOK_URL:
            send_alert_slack(slack_message)
        else:
            # For debugging slack message
            LOGGER.info("https://app.slack.com/block-kit-builder/#%s", parse.quote(slack_message))


def send_alert_slack(message):
    try:
        request = Request(WEBHOOK_URL, message)
        response = urlopen(request)
        response.read()
    except HTTPError as err:
        raise Exception(err)
    except URLError as err:
        raise Exception(err)


def prepare_slack_message(message):
    name = message['AlarmName']
    description = message['AlarmDescription']

    old_state = message['OldStateValue']
    new_state = message['NewStateValue']

    reason = message['NewStateReason']

    region = message['AlarmArn'].split(':')[3]  # arn:aws:cloudwatch:us-east-1:AWS_ACCOUNT_ID:alarm:ALARM_NAME

    link = LINK.format(region, parse.quote_plus(name, safe='()'))

    trigger = message['Trigger']

    dimensions = ', '.join(map(lambda dim: dim['name'] + ': ' + dim['value'], trigger['Dimensions'])) \
        if 'Dimensions' in trigger else None

    trigger_operator = OPERATORS.get(trigger['ComparisonOperator'], UNKNOWN_OPERATOR)

    trigger_unit = ' ' + str(trigger['Unit']).lower() if trigger['Unit'] else ''

    trigger = '{} {} {} {}{} for {} period(s) of {} seconds.' \
        .format(trigger['Statistic'].capitalize(), trigger['MetricName'], trigger_operator, trigger['Threshold'],
                trigger_unit, trigger['EvaluationPeriods'], trigger['Period'], )

    timestamp = int(round(datetime.timestamp(datetime.strptime(message['StateChangeTime'], '%Y-%m-%dT%H:%M:%S.%f%z'))))

    return construct_slack_message(name, description, trigger, dimensions, reason,
                                   old_state, new_state, link, timestamp)


def construct_slack_message(name, description, trigger, dimensions,
                            reason, old_state, new_state, link, timestamp):
    message_attachments = [construct_slack_message_text_section('Name', name)]

    if description:
        message_attachments.append(construct_slack_message_text_section('Description', description))

    message_attachments.extend([
        construct_slack_message_text_section('Trigger', trigger),
        construct_slack_message_text_section('State change reason', reason)
    ])

    if dimensions:
        message_attachments.append(construct_slack_message_text_section('Dimension(s)', dimensions))

    message_attachments.extend([
        construct_slack_message_fields_section(
            construct_slack_message_markdown('Previous state', old_state),
            construct_slack_message_markdown('New state', new_state)
        ),
        construct_slack_message_text_section('Link to alarm', link),
        {
            'type': 'context',
            'elements': [
                construct_slack_message_markdown(None, '<!date^' + str(timestamp) + '^ {date} at {time}| >')
            ]
        }
    ])

    message = {
        'attachments': [
            {
                'color': COLORS.get(new_state, UNKNOWN_COLOR),
                'blocks': message_attachments
            }
        ]
    }
    LOGGER.info('Slack message: \n%s', message)
    return json.dumps(message).encode('utf-8')


def construct_slack_message_text_section(title, value):
    return {
        'type': 'section',
        'text': construct_slack_message_markdown(title, value)
    }


def construct_slack_message_fields_section(*fields):
    return {
        'type': 'section',
        'fields': fields
    }


def construct_slack_message_markdown(title, value):
    title = (('*' + title + ':*\n') if title else '')
    return {
        'type': 'mrkdwn',
        'text': title + value
    }
