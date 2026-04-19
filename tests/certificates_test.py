import datetime
import dateutil.parser
import pytest

def certificate_info(server, certificate):
    openssl_result = server.run(f"openssl x509 -in {certificate} -noout -enddate -dateopt iso_8601 -subject -issuer")
    return dict([x.split('=', 1) for x in openssl_result.stdout.splitlines()])

@pytest.mark.parametrize("certificate_type", ['ca_certificate', 'server_certificate', 'client_certificate', 'candlepin_certificate'])
def test_certificate_expiry(server, certificates, certificate_type):
    cert_path = certificates.get(certificate_type)
    if cert_path is None:
        pytest.skip(f"{certificate_type} not configured")
    openssl_data = certificate_info(server, cert_path)
    not_after = dateutil.parser.parse(openssl_data['notAfter'])
    now = datetime.datetime.now(tz=not_after.tzinfo)
    assert not_after - now > datetime.timedelta(days=365*10)
