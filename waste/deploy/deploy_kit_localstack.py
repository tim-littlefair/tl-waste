import ifaddr
import boto3

_preferred_ip = None

def _select_ipv4_address():
    global _preferred_ip
    if _preferred_ip is None:
        for ad in ifaddr.get_adapters():
            for ip in ad.ips:
                if isinstance(ip.ip,tuple):
                    # ipv6 address, not interested 
                    continue
                elif ip.ip == "127.0.0.1":
                    # loopback, prefer not
                    continue
                elif ip.ip.startswith("172."):
                    # internal, prefer not
                    continue
                else:
                    _preferred_ip = ip.ip
        # if all else fails select the loopback interface
        if _preferred_ip is None:
            _preferred_ip = "127.0.0.1"
    print("Preferred IP address:",_preferred_ip)
    return _preferred_ip

class Factory:
    def __init__(
            self,
            region_name=,
            ipv4_address=None,
        ):
        self.region_name = region_name
        self.ipv4_address = ipv4_address or _select_ipv4_address()
        self.clients = { }
        self._create_client("iam",4593)
        self._create_client("s3",4572)
        self._create_client("lambda",4574)
        self._create_client("apigateway",4567)
    
    def _create_client(self,aws_service_name, port=51492):
        client = boto3.client(
            aws_service_name,
            endpoint_url='http://%s:%d'%(self.ipv4_address,port),
            region_name=self.region_name
        )
        self.clients[aws_service_name] = client
        return client

    def get_client(self,service_name):
        return self.clients.get(service_name)

    def get_region_name(self):
        return self.region_name

    def get_integration_arn(self,fn_arn):
     return ":".join([
        "arn:aws:apigateway",
        self.region_name,
        "lambda:path/2015-03-31/functions/"
    ]) + fn_arn + "/invocations"
       
    def get_lambda_environment(self):
        return { 'Variables' : { '_LS_HOST': self.ipv4_address } }

    def get_api_url(self,
        api_id, stage_id,
        resource_id, resource_name,
        hostname = None,
    ):
        url1 = "http://%s:4567/restapis/%s/%s/_user_request_/%s" % ( 
            self.ipv4_address, api_id, stage_id, resource_name 
        )  
        print("localstack url:",url1)
        return url1
    
    def get_app_bucket_name(self):
        return self.app_bucket_name

if __name__ == "__main__":
    print("dkl invoked")


