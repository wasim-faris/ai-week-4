from rest_framework import serializers


class GenerateEmailSerializer(serializers.Serializer):
    message = serializers.CharField(max_length=4000, trim_whitespace=True)
    recipient = serializers.CharField(max_length=200, required=False, allow_blank=True)
    tone = serializers.ChoiceField(
        choices=["Professional", "Friendly", "Formal", "Casual"]
    )
    instructions = serializers.CharField(
        max_length=2000, required=False, allow_blank=True
    )
    mode = serializers.ChoiceField(choices=["baseline", "improved"])

    def validate_message(self, value):
        if not value.strip():
            raise serializers.ValidationError("Enter the email purpose or message.")
        return value.strip()