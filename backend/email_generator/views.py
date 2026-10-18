from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .serializers import GenerateEmailSerializer
from .services import (
    EmailGenerationError,
    ProviderConfigurationError,
    ProviderAuthenticationError,
    ProviderModelError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    generate_email,
)


@api_view(["POST"])
def generate_email_view(request):
    serializer = GenerateEmailSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(
            {"error": "Please check the submitted fields.", "details": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        result = generate_email(serializer.validated_data)
    except ProviderAuthenticationError as error:
        return Response({"error": str(error)}, status=status.HTTP_502_BAD_GATEWAY)
    except ProviderModelError as error:
        return Response({"error": str(error)}, status=status.HTTP_502_BAD_GATEWAY)
    except ProviderConfigurationError as error:
        return Response({"error": str(error)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    except ProviderRateLimitError as error:
        return Response({"error": str(error)}, status=status.HTTP_429_TOO_MANY_REQUESTS)
    except ProviderTimeoutError as error:
        return Response({"error": str(error)}, status=status.HTTP_504_GATEWAY_TIMEOUT)
    except EmailGenerationError as error:
        return Response({"error": str(error)}, status=status.HTTP_502_BAD_GATEWAY)

    return Response(result, status=status.HTTP_200_OK)