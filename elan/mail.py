import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage

def send_mail(recipients, cc_recipients=None, bcc_recipients=None,  text='', html=None, sender='', mail_subject='', mail_from='"ELAN Agent"', embedded=None):
    '''
    Sends a mail to recipients, cc_recipients and bcc_recipients using text or html or both as alternate.
    embedded can be added using embedded as a dict of {cid: path} where cid is the embedded object cid used in html to refer to it (<img src="cid:<cid>">) and path is the path to the file
    '''
    # TODO: files can be added using images as a dict of {filename: path} where filename is the name displayed in the mail and path is the path to the file
    if cc_recipients is None:
        cc_recipients = []
    if bcc_recipients is None:
        bcc_recipients = []
    if embedded is None:
        embedded = {}
        
    if not isinstance(recipients, list):
        recipients = [recipients]
    if not isinstance(cc_recipients, list):
        cc_recipients = [cc_recipients]
    if not isinstance(bcc_recipients, list):
        bcc_recipients = [bcc_recipients]

    if embedded:
        html_msg = MIMEMultipart('related')
        html_msg.attach(MIMEText(html, 'html'))
        # Attach embedded
        for cid in embedded:
            file_path = embedded[cid]
            with open(file_path, 'rb') as fp:
                embedded_msg = MIMEImage(fp.read())
            html_msg.attach(embedded_msg)            
    else:
        html_msg = MIMEText(html, 'html')


    if html and text:
        msg = MIMEMultipart('alternative')
        msg.attach(MIMEText(text, 'plain'))
        msg.attach(html_msg) # Last is best and preferred according to RFC 2046
    elif html:
        msg = html_msg
    else:
        msg = MIMEText(text, 'plain')
        

    msg['From'] = mail_from
    for recipient in recipients:
        msg['To'] = recipient  # some magic here...
    for recipient in cc_recipients:
        msg['CC'] = recipient  # some magic here...
    msg['Subject'] = mail_subject
    

    s = smtplib.SMTP('localhost')
    
    s.sendmail(sender, recipients + cc_recipients + bcc_recipients, msg.as_string())
    s.quit()
