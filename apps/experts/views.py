from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Avg, Q
from django.http import JsonResponse
from django.utils import timezone

from .models import ExpertProfile, ExpertTask, ExpertSession, ExpertSpecialty
from apps.annotations.models import Annotation, ExpertFeedback
from apps.core.models import RegulatoryEntity


@login_required
def experts_dashboard(request):
    """Dashboard des experts"""
    experts = ExpertProfile.objects.select_related('user').filter(is_active=True)

    # Statistiques globales
    stats = {
        'total_experts': experts.count(),
        'active_experts': experts.filter(last_activity__gte=timezone.now().date()).count(),
        'total_validations': sum(expert.total_annotations_validated for expert in experts),
        'avg_accuracy': experts.aggregate(avg=Avg('accuracy_score'))['avg'] or 0,
    }

    # Top experts
    top_experts = experts.order_by('-total_annotations_validated')[:5]

    # Tâches récentes
    recent_tasks = ExpertTask.objects.select_related('expert__user').order_by('-created_at')[:10]

    context = {
        'stats': stats,
        'experts': experts,
        'top_experts': top_experts,
        'recent_tasks': recent_tasks,
    }

    return render(request, 'experts/dashboard.html', context)


@login_required
def expert_list(request):
    """Liste des experts"""
    experts = ExpertProfile.objects.select_related('user').all()

    # Filtres
    expertise_level = request.GET.get('expertise_level')
    specialization = request.GET.get('specialization')
    is_active = request.GET.get('is_active')

    if expertise_level:
        experts = experts.filter(expertise_level=expertise_level)
    if specialization:
        experts = experts.filter(specializations__contains=[specialization])
    if is_active:
        experts = experts.filter(is_active=is_active.lower() == 'true')

    # Pagination
    paginator = Paginator(experts, 15)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'expertise_levels': ExpertProfile.EXPERTISE_LEVELS,
        'specializations': ExpertProfile.SPECIALIZATIONS,
        'current_filters': {
            'expertise_level': expertise_level,
            'specialization': specialization,
            'is_active': is_active,
        }
    }

    return render(request, 'experts/expert_list.html', context)


@login_required
def expert_detail(request, expert_id):
    """Détail d'un expert"""
    expert = get_object_or_404(ExpertProfile, id=expert_id)

    # Mettre à jour les statistiques
    expert.update_statistics()

    # Récentes activités
    recent_validations = Annotation.objects.filter(
        validated_by=expert.user
    ).order_by('-validated_at')[:10]

    recent_feedbacks = ExpertFeedback.objects.filter(
        expert=expert.user
    ).order_by('-created_at')[:10]

    # Tâches assignées
    tasks = expert.tasks.all().order_by('-created_at')[:10]

    # Spécialités
    specialties = expert.specialties.select_related('entity_type').all()

    context = {
        'expert': expert,
        'recent_validations': recent_validations,
        'recent_feedbacks': recent_feedbacks,
        'tasks': tasks,
        'specialties': specialties,
    }

    return render(request, 'experts/expert_detail.html', context)


@login_required
def create_expert_profile(request):
    """Créer un profil d'expert"""
    if request.method == 'POST':
        user_id = request.POST.get('user_id')
        expertise_level = request.POST.get('expertise_level')
        company = request.POST.get('company', '')
        position = request.POST.get('position', '')
        years_experience = int(request.POST.get('years_experience', 0))

        try:
            user = User.objects.get(id=user_id)

            # Vérifier si le profil existe déjà
            if hasattr(user, 'expert_profile'):
                messages.error(request, 'Cet utilisateur a déjà un profil expert.')
                return redirect('experts:expert_list')

            profile = ExpertProfile.objects.create(
                user=user,
                expertise_level=expertise_level,
                company=company,
                position=position,
                years_experience=years_experience
            )

            messages.success(request, f'Profil expert créé pour {user.username}.')
            return redirect('experts:expert_detail', expert_id=profile.id)

        except User.DoesNotExist:
            messages.error(request, 'Utilisateur introuvable.')

    # GET request
    users_without_profile = User.objects.filter(expert_profile__isnull=True)

    context = {
        'users': users_without_profile,
        'expertise_levels': ExpertProfile.EXPERTISE_LEVELS,
        'specializations': ExpertProfile.SPECIALIZATIONS,
    }

    return render(request, 'experts/create_profile.html', context)


@login_required
def expert_tasks(request, expert_id):
    """Tâches d'un expert"""
    expert = get_object_or_404(ExpertProfile, id=expert_id)
    tasks = expert.tasks.all().order_by('-created_at')

    # Filtres
    status = request.GET.get('status')
    task_type = request.GET.get('task_type')

    if status:
        tasks = tasks.filter(status=status)
    if task_type:
        tasks = tasks.filter(task_type=task_type)

    # Pagination
    paginator = Paginator(tasks, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'expert': expert,
        'page_obj': page_obj,
        'task_types': ExpertTask.TASK_TYPES,
        'status_choices': ExpertTask.STATUS_CHOICES,
        'current_filters': {'status': status, 'task_type': task_type},
    }

    return render(request, 'experts/expert_tasks.html', context)


@login_required
def assign_task(request):
    """Assigner une tâche à un expert"""
    if request.method == 'POST':
        expert_id = request.POST.get('expert_id')
        task_type = request.POST.get('task_type')
        title = request.POST.get('title')
        description = request.POST.get('description')
        priority = request.POST.get('priority', 'normal')
        document_id = request.POST.get('document_id')

        try:
            expert = ExpertProfile.objects.get(id=expert_id)

            task = ExpertTask.objects.create(
                expert=expert,
                task_type=task_type,
                title=title,
                description=description,
                priority=priority,
                created_by=request.user
            )

            if document_id:
                from apps.documents.models import Document
                document = Document.objects.get(id=document_id)
                task.document = document
                task.save()

            messages.success(request, f'Tâche assignée à {expert.user.username}.')
            return redirect('experts:expert_tasks', expert_id=expert.id)

        except (ExpertProfile.DoesNotExist, Exception) as e:
            messages.error(request, f'Erreur lors de l\'assignation: {e}')

    # GET request
    experts = ExpertProfile.objects.filter(is_active=True)
    from apps.documents.models import Document
    documents = Document.objects.all()[:100]  # Limiter pour performance

    context = {
        'experts': experts,
        'documents': documents,
        'task_types': ExpertTask.TASK_TYPES,
        'priority_choices': ExpertTask.PRIORITY_CHOICES,
    }

    return render(request, 'experts/assign_task.html', context)


@login_required
def expert_analytics(request, expert_id):
    """Analytics d'un expert"""
    expert = get_object_or_404(ExpertProfile, id=expert_id)

    # Mise à jour des stats
    expert.update_statistics()

    # Analytics par entité
    entity_stats = {}
    for specialty in expert.specialties.select_related('entity_type'):
        entity_stats[specialty.entity_type.name] = {
            'proficiency': specialty.proficiency_level,
            'annotations': specialty.annotations_count,
            'success_rate': specialty.success_rate,
        }

    # Evolution dans le temps (simulation)
    monthly_stats = []
    for i in range(6):
        month_data = {
            'month': f'Mois {i + 1}',
            'validations': expert.total_annotations_validated // 6 + i * 2,
            'feedbacks': expert.total_feedbacks_given // 6 + i,
            'accuracy': min(expert.accuracy_score + i, 98),
        }
        monthly_stats.append(month_data)

    context = {
        'expert': expert,
        'entity_stats': entity_stats,
        'monthly_stats': monthly_stats,
    }

    return render(request, 'experts/expert_analytics.html', context)


# API Views
@login_required
def api_expert_stats(request, expert_id):
    """API pour les statistiques d'expert"""
    expert = get_object_or_404(ExpertProfile, id=expert_id)
    expert.update_statistics()

    data = {
        'total_validations': expert.total_annotations_validated,
        'total_feedbacks': expert.total_feedbacks_given,
        'accuracy_score': expert.accuracy_score,
        'validation_rate': expert.validation_rate,
        'avg_validation_time': expert.average_validation_time,
    }

    return JsonResponse(data)