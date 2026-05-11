import os
import weaviate


def get_weaviate_client() -> weaviate.WeaviateClient:
    host = os.environ.get("WEAVIATE_HOST", "localhost")
    port = int(os.environ.get("WEAVIATE_PORT", "8080"))
    grpc_port = int(os.environ.get("WEAVIATE_GRPC_PORT", "50051"))
    return weaviate.connect_to_local(host=host, port=port, grpc_port=grpc_port)
