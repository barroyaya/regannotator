# apps/ml/views.py
import json
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.core.paginator import Paginator
from django.db.models import Count, Avg, Q
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone

from .models import ModelTraining, ModelVersion, ExpertRule
from .services import MLTrainingService, ExpertRuleEngine
from apps.annotations.models import Annotation
from apps.core.models import RegulatoryEntity


# =============================================================================
# VUES PRINCIPALES - DASHBOARD ET ENTRAÎNEMENTS
# =============================================================================

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Avg
from django.shortcuts import render
from .models import ModelTraining, ModelVersion, ExpertRule, Annotation

@login_required
def training_dashboard(request):
    """Dashboard d'entraînement ML"""
    trainings = ModelTraining.objects.all().order_by('-created_at')[:10]
    rules = ExpertRule.objects.filter(is_active=True)[:5]

    # Ajoute un attribut `confidence_percent` pour chaque règle
    for rule in rules:
        rule.confidence_percent = round(rule.confidence_score * 100, 2) if rule.confidence_score is not None else 0

    # Statistiques générales
    stats = {
        'total_annotations': Annotation.objects.filter(validation_status='validated').count(),
        'total_trainings': ModelTraining.objects.count(),
        'active_models': ModelVersion.objects.filter(is_active=True).count(),
        'active_rules': ExpertRule.objects.filter(is_active=True).count(),
        'avg_accuracy': ModelTraining.objects.filter(
            status='completed'
        ).aggregate(avg=Avg('accuracy_score'))['avg'] or 0,
    }

    # Entraînements récents par statut
    training_stats = ModelTraining.objects.values('status').annotate(
        count=Count('id')
    ).order_by('status')

    context = {
        'trainings': trainings,
        'rules': rules,
        'stats': stats,
        'training_stats': training_stats,
    }

    return render(request, 'ml/training_dashboard.html', context)


@login_required
def create_training(request):
    """Créer une nouvelle session d'entraînement"""
    if request.method == 'POST':
        name = request.POST.get('name')
        description = request.POST.get('description', '')
        validation_split = float(request.POST.get('validation_split', 0.2)) / 100

        # Paramètres du modèle
        model_params = {
            'epochs': int(request.POST.get('epochs', 20)),
            'batch_size': int(request.POST.get('batch_size', 32)),
            'learning_rate': float(request.POST.get('learning_rate', 0.01)),
            'algorithm': request.POST.get('algorithm', 'bert'),
            'early_stopping': request.POST.get('early_stopping') == 'on',
            'data_augmentation': request.POST.get('data_augmentation') == 'on',
        }

        # Créer la session d'entraînement
        training = ModelTraining.objects.create(
            name=name,
            description=description,
            validation_split=validation_split,
            model_parameters=model_params,
            created_by=request.user
        )

        # Ajouter toutes les annotations validées
        validated_annotations = Annotation.objects.filter(validation_status='validated')
        training.training_annotations.set(validated_annotations)

        # Démarrer l'entraînement
        try:
            service = MLTrainingService()
            service.train_model(training)
            messages.success(request, f"Modèle '{name}' entraîné avec succès!")
            return redirect('ml:training_detail', training_id=training.id)
        except Exception as e:
            messages.error(request, f"Erreur lors de l'entraînement: {e}")
            return redirect('ml:training_dashboard')

    # GET request - afficher le formulaire
    total_annotations = Annotation.objects.filter(validation_status='validated').count()
    entity_stats = Annotation.objects.filter(
        validation_status='validated'
    ).values('entity_type__name').annotate(count=Count('id'))

    context = {
        'total_annotations': total_annotations,
        'entity_stats': entity_stats,
    }

    return render(request, 'ml/create_training.html', context)


@login_required
def training_detail(request, training_id):
    """Détail d'une session d'entraînement"""
    training = get_object_or_404(ModelTraining, id=training_id)

    # Métriques par entité
    entity_metrics = training.entity_metrics

    # Versions du modèle
    versions = training.modelversion_set.all().order_by('-created_at')

    context = {
        'training': training,
        'entity_metrics': entity_metrics,
        'versions': versions,
    }

    return render(request, 'ml/training_detail.html', context)


@login_required
def training_metrics(request, training_id):
    """Métriques détaillées d'un entraînement"""
    training = get_object_or_404(ModelTraining, id=training_id)

    if training.status != 'completed':
        messages.warning(request, 'Les métriques ne sont disponibles que pour les entraînements terminés.')
        return redirect('ml:training_detail', training_id=training.id)

    context = {
        'training': training,
        'entity_metrics': training.entity_metrics,
    }

    return render(request, 'ml/training_metrics.html', context)


# =============================================================================
# VUES MODÈLES
# =============================================================================

@login_required
def model_list(request):
    """Liste des modèles"""
    models = ModelVersion.objects.select_related('training').all().order_by('-created_at')

    # Filtres
    status_filter = request.GET.get('status')
    if status_filter:
        if status_filter == 'active':
            models = models.filter(is_active=True)
        elif status_filter == 'inactive':
            models = models.filter(is_active=False)

    # Pagination
    paginator = Paginator(models, 15)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'current_filter': status_filter,
    }

    return render(request, 'ml/model_list.html', context)


@login_required
def model_detail(request, model_id):
    """Détail d'un modèle"""
    model = get_object_or_404(ModelVersion, id=model_id)

    context = {
        'model': model,
        'training': model.training,
    }

    return render(request, 'ml/model_detail.html', context)


@login_required
def deploy_model(request, model_id):
    """Déployer un modèle"""
    model = get_object_or_404(ModelVersion, id=model_id)

    if request.method == 'POST':
        # Désactiver tous les autres modèles
        ModelVersion.objects.all().update(is_active=False)

        # Activer ce modèle
        model.is_active = True
        model.save()

        messages.success(request, f'Modèle {model.version} déployé avec succès!')
        return redirect('ml:model_detail', model_id=model.id)

    context = {'model': model}
    return render(request, 'ml/deploy_model.html', context)


# =============================================================================
# VUES RÈGLES EXPERTES
# =============================================================================

@login_required
def expert_rules_list(request):
    """Liste des règles expertes"""
    rules = ExpertRule.objects.select_related('entity_type').all().order_by('-created_at')

    # Filtres
    entity_filter = request.GET.get('entity')
    rule_type_filter = request.GET.get('rule_type')
    is_active_filter = request.GET.get('is_active')

    if entity_filter:
        rules = rules.filter(entity_type_id=entity_filter)
    if rule_type_filter:
        rules = rules.filter(rule_type=rule_type_filter)
    if is_active_filter:
        rules = rules.filter(is_active=is_active_filter.lower() == 'true')

    # Pagination
    paginator = Paginator(rules, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Options pour les filtres
    entities = RegulatoryEntity.objects.filter(is_active=True)
    rule_types = ExpertRule.RULE_TYPES

    context = {
        'page_obj': page_obj,
        'entities': entities,
        'rule_types': rule_types,
        'current_filters': {
            'entity': entity_filter,
            'rule_type': rule_type_filter,
            'is_active': is_active_filter,
        }
    }

    return render(request, 'ml/expert_rules_list.html', context)


@login_required
def create_expert_rule(request):
    """Créer une nouvelle règle experte"""
    if request.method == 'POST':
        name = request.POST.get('name')
        entity_type_id = request.POST.get('entity_type_id')
        rule_type = request.POST.get('rule_type')
        pattern = request.POST.get('pattern')
        confidence_score = float(request.POST.get('confidence_score', 1.0))

        try:
            entity_type = RegulatoryEntity.objects.get(id=entity_type_id)

            rule = ExpertRule.objects.create(
                name=name,
                entity_type=entity_type,
                rule_type=rule_type,
                pattern=pattern,
                confidence_score=confidence_score,
                created_by=request.user
            )

            messages.success(request, f'Règle "{name}" créée avec succès!')
            return redirect('ml:rule_detail', rule_id=rule.id)

        except RegulatoryEntity.DoesNotExist:
            messages.error(request, 'Type d\'entité invalide.')
        except Exception as e:
            messages.error(request, f'Erreur lors de la création: {e}')

    # GET request
    entities = RegulatoryEntity.objects.filter(is_active=True)
    rule_types = ExpertRule.RULE_TYPES

    context = {
        'entities': entities,
        'rule_types': rule_types,
    }

    return render(request, 'ml/create_expert_rule.html', context)


@login_required
def rule_detail(request, rule_id):
    """Détail d'une règle experte"""
    rule = get_object_or_404(ExpertRule, id=rule_id)

    context = {'rule': rule}
    return render(request, 'ml/rule_detail.html', context)


@login_required
def edit_rule(request, rule_id):
    """Éditer une règle experte"""
    rule = get_object_or_404(ExpertRule, id=rule_id)

    if request.method == 'POST':
        rule.name = request.POST.get('name')
        rule.pattern = request.POST.get('pattern')
        rule.confidence_score = float(request.POST.get('confidence_score', 1.0))
        rule.is_active = request.POST.get('is_active') == 'on'

        try:
            entity_type_id = request.POST.get('entity_type_id')
            rule.entity_type = RegulatoryEntity.objects.get(id=entity_type_id)
            rule.save()

            messages.success(request, 'Règle mise à jour avec succès!')
            return redirect('ml:rule_detail', rule_id=rule.id)

        except Exception as e:
            messages.error(request, f'Erreur lors de la mise à jour: {e}')

    entities = RegulatoryEntity.objects.filter(is_active=True)
    context = {
        'rule': rule,
        'entities': entities,
    }

    return render(request, 'ml/edit_rule.html', context)


@login_required
def delete_rule(request, rule_id):
    """Supprimer une règle experte"""
    rule = get_object_or_404(ExpertRule, id=rule_id)

    if request.method == 'POST':
        rule_name = rule.name
        rule.delete()
        messages.success(request, f'Règle "{rule_name}" supprimée avec succès!')
        return redirect('ml:expert_rules')

    context = {'rule': rule}
    return render(request, 'ml/delete_rule.html', context)


# =============================================================================
# VUES ANALYTICS ET PERFORMANCE
# =============================================================================

@login_required
def ml_analytics(request):
    """Analytics ML générales"""
    # Stats par entité
    entity_performance = {}
    for entity in RegulatoryEntity.objects.filter(is_active=True):
        # Simuler des métriques de performance
        entity_performance[entity.name] = {
            'precision': 0.85 + (hash(entity.name) % 10) / 100,
            'recall': 0.80 + (hash(entity.name) % 15) / 100,
            'f1_score': 0.82 + (hash(entity.name) % 12) / 100,
            'annotations_count': Annotation.objects.filter(
                entity_type=entity, validation_status='validated'
            ).count()
        }

    # Évolution des modèles
    training_evolution = ModelTraining.objects.filter(
        status='completed'
    ).order_by('created_at').values(
        'name', 'accuracy_score', 'created_at'
    )

    context = {
        'entity_performance': entity_performance,
        'training_evolution': list(training_evolution),
    }

    return render(request, 'ml/analytics.html', context)


@login_required
def model_performance(request):
    """Performance des modèles"""
    completed_trainings = ModelTraining.objects.filter(
        status='completed'
    ).order_by('-accuracy_score')

    # Calcul de statistiques
    performance_stats = {
        'best_accuracy': completed_trainings.first().accuracy_score if completed_trainings else 0,
        'avg_accuracy': completed_trainings.aggregate(avg=Avg('accuracy_score'))['avg'] or 0,
        'total_models': completed_trainings.count(),
    }

    context = {
        'trainings': completed_trainings,
        'performance_stats': performance_stats,
    }

    return render(request, 'ml/model_performance.html', context)


@login_required
def model_benchmarks(request):
    """Benchmarks des modèles"""
    # Comparer les performances des différents algorithmes
    algorithm_performance = {}
    for training in ModelTraining.objects.filter(status='completed'):
        algorithm = training.model_parameters.get('algorithm', 'unknown')
        if algorithm not in algorithm_performance:
            algorithm_performance[algorithm] = {
                'count': 0,
                'avg_accuracy': 0,
                'avg_training_time': 0,
                'accuracies': []
            }

        algorithm_performance[algorithm]['count'] += 1
        algorithm_performance[algorithm]['accuracies'].append(training.accuracy_score or 0)

    # Calculer les moyennes
    for algo, stats in algorithm_performance.items():
        if stats['accuracies']:
            stats['avg_accuracy'] = sum(stats['accuracies']) / len(stats['accuracies'])

    context = {
        'algorithm_performance': algorithm_performance,
    }

    return render(request, 'ml/benchmarks.html', context)


# =============================================================================
# VUES API
# =============================================================================

@login_required
def api_training_status(request, training_id):
    """API pour obtenir le statut d'un entraînement"""
    training = get_object_or_404(ModelTraining, id=training_id)

    data = {
        'id': training.id,
        'name': training.name,
        'status': training.status,
        'accuracy_score': training.accuracy_score,
        'precision_score': training.precision_score,
        'recall_score': training.recall_score,
        'f1_score': training.f1_score,
        'created_at': training.created_at.isoformat(),
    }

    return JsonResponse(data)


@login_required
@csrf_exempt
def api_model_predict(request, model_id):
    """API pour faire des prédictions avec un modèle"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    model = get_object_or_404(ModelVersion, id=model_id)

    try:
        data = json.loads(request.body)
        text = data.get('text', '')

        if not text:
            return JsonResponse({'error': 'Text is required'}, status=400)

        # Ici vous intégreriez votre logique de prédiction réelle
        # Pour la démo, on simule des prédictions
        predictions = [
            {
                'entity_type': 'VARIATION_CODE',
                'text_value': 'Article L.123-4',
                'start_position': 0,
                'end_position': 13,
                'confidence_score': 0.95
            }
        ]

        return JsonResponse({
            'predictions': predictions,
            'model_id': model.id,
            'model_version': model.version
        })

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@csrf_exempt
def api_test_rule(request):
    """API pour tester une règle experte"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        data = json.loads(request.body)
        pattern = data.get('pattern', '')
        rule_type = data.get('rule_type', 'pattern')
        test_text = data.get('test_text', '')

        if not pattern or not test_text:
            return JsonResponse({'error': 'Pattern and test_text are required'}, status=400)

        # Créer une règle temporaire pour le test
        temp_rule = ExpertRule(
            pattern=pattern,
            rule_type=rule_type,
            confidence_score=1.0
        )

        # Utiliser le moteur de règles pour tester
        engine = ExpertRuleEngine()
        matches = engine._apply_single_rule(temp_rule, test_text)

        return JsonResponse({
            'matches': matches,
            'match_count': len(matches)
        })

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# =============================================================================
# VUES EXPORT/IMPORT
# =============================================================================

@login_required
def export_model(request, model_id):
    """Exporter un modèle"""
    model = get_object_or_404(ModelVersion, id=model_id)

    # Ici vous intégreriez votre logique d'export réelle
    # Pour la démo, on retourne un JSON simple
    export_data = {
        'model_id': model.id,
        'version': model.version,
        'training_name': model.training.name,
        'accuracy_score': model.training.accuracy_score,
        'model_parameters': model.training.model_parameters,
        'export_date': timezone.now().isoformat(),
    }

    response = HttpResponse(
        json.dumps(export_data, indent=2),
        content_type='application/json'
    )
    response['Content-Disposition'] = f'attachment; filename="model_{model.id}_export.json"'

    return response


@login_required
def import_model(request):
    """Importer un modèle"""
    if request.method == 'POST':
        uploaded_file = request.FILES.get('model_file')

        if not uploaded_file:
            messages.error(request, 'Aucun fichier sélectionné.')
            return redirect('ml:model_list')

        try:
            # Ici vous intégreriez votre logique d'import réelle
            file_content = uploaded_file.read().decode('utf-8')
            import_data = json.loads(file_content)

            # Simuler l'import
            messages.success(request, 'Modèle importé avec succès!')
            return redirect('ml:model_list')

        except json.JSONDecodeError:
            messages.error(request, 'Fichier JSON invalide.')
        except Exception as e:
            messages.error(request, f'Erreur lors de l\'import: {e}')

    return render(request, 'ml/import_model.html')