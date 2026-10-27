import time
import unittest
from jobs_service.gmail import match_message, extract_otp


class MailTests(unittest.TestCase):
    def setUp(self):
        self.now=int(time.time())
        self.message={'internalDate':str(self.now*1000),'payload':{'headers':[{'name':'Authentication-Results','value':'mx.google.com; dmarc=pass header.from=portal.example'},{'name':'From','value':'Portal <verify@portal.example>'},{'name':'To','value':'candidate@example.invalid'},{'name':'Subject','value':'Verify application ABC-123'}]}}

    def test_correlate_recipient_sender_time_requisition(self):
        args=('candidate@example.invalid',{'portal.example'},'ABC-123',self.now-10)
        self.assertTrue(match_message(self.message,*args))
        self.assertFalse(match_message(self.message,'other@example.invalid',*args[1:]))
        self.assertFalse(match_message(self.message,args[0],{'evil.example'},*args[2:]))
        self.assertFalse(match_message(self.message,*args[:2],'OTHER-456',args[3]))
        self.assertFalse(match_message(self.message,*args[:3],self.now+1))

    def test_code_not_taken_from_other_mail_or_expired(self):
        self.assertEqual(extract_otp(self.message,'Your verification code is 123456', 'candidate@example.invalid',{'portal.example'},'ABC-123',self.now-10),'123456')
        self.assertIsNone(extract_otp(self.message,'code 123456', 'candidate@example.invalid',{'portal.example'},'OTHER',self.now-10))
        self.assertIsNone(extract_otp(self.message,'code 123456', 'candidate@example.invalid',{'portal.example'},'ABC-123',self.now-1000))

    def test_requisition_boundary_purpose_and_authenticated_sender(self):
        args=('candidate@example.invalid',{'portal.example'},'123',self.now-10)
        headers=self.message['payload']['headers']
        headers[-1]['value']='Verify application 91234'
        self.assertFalse(match_message(self.message,*args))
        headers[-1]['value']='Password reset for account 123'
        self.assertFalse(match_message(self.message,*args))
        headers[-1]['value']='Verify application 123'
        headers[0]['value']='mx.google.com; dmarc=fail header.from=portal.example'
        self.assertFalse(match_message(self.message,*args))
