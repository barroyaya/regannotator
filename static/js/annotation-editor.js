
class AnnotationEditor {
    constructor(containerSelector) {
        this.container = document.querySelector(containerSelector);
        this.currentSentence = null;
        this.selectedText = '';
        this.annotations = [];
        this.entityTypes = [];
        this.init();
    }

    async init() {
        await this.loadEntityTypes();
        this.setupEventListeners();
        this.setupKeyboardShortcuts();
    }

    async loadEntityTypes() {
        try {
            const response = await fetch('/api/entity-types/');
            this.entityTypes = await response.json();
        } catch (error) {
            console.error('Erreur lors du chargement des types d\'entités:', error);
        }
    }

    setupEventListeners() {
        // Sélection de texte
        document.addEventListener('mouseup', (e) => {
            const selection = window.getSelection();
            if (selection.toString().length > 0) {
                this.handleTextSelection(selection);
            }
        });

        // Validation des annotations
        document.addEventListener('click', (e) => {
            if (e.target.classList.contains('validate-btn')) {
                this.validateAnnotation(e.target.dataset.annotationId);
            }
            if (e.target.classList.contains('reject-btn')) {
                this.rejectAnnotation(e.target.dataset.annotationId);
            }
        });
    }

    setupKeyboardShortcuts() {
        document.addEventListener('keydown', (e) => {
            // Ctrl + 1-9 pour assigner rapidement des entités
            if (e.ctrlKey && e.key >= '1' && e.key <= '9') {
                e.preventDefault();
                const entityIndex = parseInt(e.key) - 1;
                if (entityIndex < this.entityTypes.length) {
                    this.quickAnnotate(this.entityTypes[entityIndex]);
                }
            }

            // Ctrl + V pour valider
            if (e.ctrlKey && e.key === 'v') {
                e.preventDefault();
                this.validateCurrentSelection();
            }

            // Ctrl + R pour rejeter
            if (e.ctrlKey && e.key === 'r') {
                e.preventDefault();
                this.rejectCurrentSelection();
            }
        });
    }

    handleTextSelection(selection) {
        this.selectedText = selection.toString().trim();
        if (this.selectedText.length === 0) return;

        // Calculer la position
        const range = selection.getRangeAt(0);
        const rect = range.getBoundingClientRect();

        // Afficher le popup d'annotation
        this.showAnnotationPopup(rect);
    }

    showAnnotationPopup(rect) {
        // Supprimer le popup existant
        const existingPopup = document.querySelector('.annotation-popup');
        if (existingPopup) existingPopup.remove();

        // Créer le nouveau popup
        const popup = document.createElement('div');
        popup.className = 'annotation-popup';
        popup.style.cssText = `
            position: fixed;
            top: ${rect.bottom + 10}px;
            left: ${rect.left}px;
            background: white;
            border: 1px solid #ccc;
            border-radius: 8px;
            padding: 10px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            z-index: 1000;
            max-width: 300px;
        `;

        // Boutons pour chaque type d'entité
        const buttonsHtml = this.entityTypes.map((entity, index) => `
            <button class="btn btn-sm btn-outline-primary me-1 mb-1" 
                    onclick="annotationEditor.createAnnotation('${entity.name}')"
                    title="Raccourci: Ctrl+${index + 1}">
                <span style="background-color: ${entity.color}; width: 12px; height: 12px; display: inline-block; border-radius: 2px; margin-right: 4px;"></span>
                ${entity.name}
            </button>
        `).join('');

        popup.innerHTML = `
            <div class="mb-2">
                <strong>Texte sélectionné:</strong><br>
                <em>"${this.selectedText}"</em>
            </div>
            <div class="mb-2">
                <strong>Choisir le type d'entité:</strong>
            </div>
            <div>
                ${buttonsHtml}
            </div>
            <div class="mt-2">
                <button class="btn btn-sm btn-secondary" onclick="annotationEditor.closePopup()">
                    <i class="fas fa-times"></i> Annuler
                </button>
            </div>
        `;

        document.body.appendChild(popup);

        // Fermer le popup en cliquant ailleurs
        setTimeout(() => {
            document.addEventListener('click', this.closePopupOnOutsideClick.bind(this), { once: true });
        }, 100);
    }

    closePopupOnOutsideClick(e) {
        const popup = document.querySelector('.annotation-popup');
        if (popup && !popup.contains(e.target)) {
            this.closePopup();
        }
    }

    closePopup() {
        const popup = document.querySelector('.annotation-popup');
        if (popup) popup.remove();
        window.getSelection().removeAllRanges();
    }

    async createAnnotation(entityType) {
        if (!this.selectedText) return;

        const selection = window.getSelection();
        const range = selection.getRangeAt(0);

        // Calculer les positions
        const sentenceElement = range.commonAncestorContainer.closest('.sentence-display');
        if (!sentenceElement) return;

        const sentenceText = sentenceElement.textContent;
        const startPosition = sentenceText.indexOf(this.selectedText);
        const endPosition = startPosition + this.selectedText.length;

        const annotationData = {
            sentence_id: sentenceElement.dataset.sentenceId,
            entity_type: entityType,
            text_value: this.selectedText,
            start_position: startPosition,
            end_position: endPosition,
            source: 'expert'
        };

        try {
            const response = await fetch('/api/annotations/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCsrfToken()
                },
                body: JSON.stringify(annotationData)
            });

            if (response.ok) {
                const annotation = await response.json();
                this.renderAnnotation(annotation);
                this.closePopup();
                this.showSuccessMessage('Annotation créée avec succès');
            } else {
                throw new Error('Erreur lors de la création de l\'annotation');
            }
        } catch (error) {
            console.error('Erreur:', error);
            this.showErrorMessage('Erreur lors de la création de l\'annotation');
        }
    }

    renderAnnotation(annotation) {
        // Mettre à jour l'affichage avec la nouvelle annotation
        const sentenceElement = document.querySelector(`[data-sentence-id="${annotation.sentence_id}"]`);
        if (sentenceElement) {
            this.highlightAnnotationInText(sentenceElement, annotation);
            this.addAnnotationToList(annotation);
        }
    }

    highlightAnnotationInText(sentenceElement, annotation) {
        const text = sentenceElement.textContent;
        const beforeText = text.substring(0, annotation.start_position);
        const annotatedText = text.substring(annotation.start_position, annotation.end_position);
        const afterText = text.substring(annotation.end_position);

        const entityType = this.entityTypes.find(e => e.name === annotation.entity_type);
        const color = entityType ? entityType.color : '#007bff';

        sentenceElement.innerHTML = `
            ${this.escapeHtml(beforeText)}
            <span class="annotation-highlight" 
                  style="background-color: ${color}20; border-left: 3px solid ${color};"
                  data-annotation-id="${annotation.id}"
                  title="${annotation.entity_type}: ${annotation.text_value}">
                ${this.escapeHtml(annotatedText)}
            </span>
            ${this.escapeHtml(afterText)}
        `;
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    getCsrfToken() {
        return document.querySelector('[name=csrfmiddlewaretoken]').value;
    }

    showSuccessMessage(message) {
        this.showToast(message, 'success');
    }

    showErrorMessage(message) {
        this.showToast(message, 'error');
    }

    showToast(message, type) {
        const toast = document.createElement('div');
        toast.className = `toast-notification toast-${type}`;
        toast.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            padding: 12px 20px;
            border-radius: 6px;
            color: white;
            background-color: ${type === 'success' ? '#28a745' : '#dc3545'};
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            z-index: 9999;
            animation: slideInRight 0.3s ease;
        `;
        toast.textContent = message;

        document.body.appendChild(toast);

        setTimeout(() => {
            toast.style.animation = 'slideOutRight 0.3s ease';
            setTimeout(() => toast.remove(), 300);
        }, 3000);
    }
}

// Initialiser l'éditeur d'annotations
document.addEventListener('DOMContentLoaded', function() {
    window.annotationEditor = new AnnotationEditor('.annotation-editor-container');
});