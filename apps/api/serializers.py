# apps/api/serializers.py
from rest_framework import serializers
from apps.documents.models import Document, DocumentSentence
from apps.annotations.models import Annotation, AnnotationSession
from apps.core.models import RegulatoryEntity


class RegulatoryEntitySerializer(serializers.ModelSerializer):
    class Meta:
        model = RegulatoryEntity
        fields = ['id', 'name', 'description', 'color', 'is_active']


class DocumentSerializer(serializers.ModelSerializer):
    source_name = serializers.CharField(source='source.name', read_only=True)
    sentences_count = serializers.IntegerField(source='sentences.count', read_only=True)
    annotations_count = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = [
            'id', 'title', 'document_type', 'source_name', 'language',
            'status', 'created_at', 'sentences_count', 'annotations_count'
        ]

    def get_annotations_count(self, obj):
        return Annotation.objects.filter(sentence__document=obj).count()


class AnnotationSerializer(serializers.ModelSerializer):
    entity_type_name = serializers.CharField(source='entity_type.name', read_only=True)
    entity_type_color = serializers.CharField(source='entity_type.color', read_only=True)

    class Meta:
        model = Annotation
        fields = [
            'id', 'entity_type', 'entity_type_name', 'entity_type_color',
            'text_value', 'start_position', 'end_position', 'confidence_score',
            'source', 'validation_status', 'created_at'
        ]


class DocumentSentenceSerializer(serializers.ModelSerializer):
    annotations = AnnotationSerializer(many=True, read_only=True)

    class Meta:
        model = DocumentSentence
        fields = ['id', 'sentence_number', 'text', 'page_number', 'annotations']


class AnnotationCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Annotation
        fields = [
            'sentence', 'entity_type', 'text_value',
            'start_position', 'end_position', 'source'
        ]

    def create(self, validated_data):
        validated_data['created_by'] = self.context['request'].user
        return super().create(validated_data)