document.addEventListener('DOMContentLoaded', () => {
  initSearchSync();
  initLiveSearch();
  initSortableTable();
  initQuickFilters();
  initSelectionControls();
  initNotifications();
  initPagination();
});

function initSearchSync() {
  const headerInput = document.getElementById('global-search');
  const sidebarInput = document.getElementById('filter-search');
  const form = document.getElementById('filters-form');
  if (!headerInput || !sidebarInput || !form) return;

  const syncValue = (source, target) => {
    if (target.value !== source.value) {
      target.value = source.value;
    }
  };

  headerInput.addEventListener('input', () => syncValue(headerInput, sidebarInput));
  sidebarInput.addEventListener('input', () => syncValue(sidebarInput, headerInput));

  headerInput.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') {
      event.preventDefault();
      syncValue(headerInput, sidebarInput);
      form.submit();
    }
  });
}

function initLiveSearch() {
  const input = document.getElementById('live-search');
  const table = document.getElementById('companies-table');
  if (!input || !table) return;

  const rows = Array.from(table.querySelectorAll('tbody tr')).filter(
    (row) => !row.querySelector('.empty-state')
  );

  const filterRows = () => {
    const query = input.value.trim().toLowerCase();
    rows.forEach((row) => {
      const text = row.innerText.toLowerCase();
      row.hidden = query ? !text.includes(query) : false;
    });
  };

  input.addEventListener('input', filterRows);
  input.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
      input.value = '';
      filterRows();
    }
  });
}

function initSortableTable() {
  const table = document.getElementById('companies-table');
  if (!table) return;

  const headers = table.querySelectorAll('thead th[data-sort]');
  const tbody = table.querySelector('tbody');
  const dataRows = Array.from(tbody.querySelectorAll('tr')).filter(
    (row) => !row.querySelector('.empty-state')
  );

  let sortState = { index: null, direction: 1 };

  headers.forEach((header, index) => {
    header.addEventListener('click', () => {
      const type = header.dataset.sort;
      let direction = 1;
      if (type !== 'number') {
        direction =
          sortState.index === index ? sortState.direction * -1 : 1;
      }
      sortState = { index, direction };

      const sortedRows = [...dataRows].sort((a, b) => {
        const result =
          type === 'number'
            ? compareNumbers(a, b, index)
            : compareText(a, b, index);
        return result * direction;
      });

      sortedRows.forEach((row) => tbody.appendChild(row));
    });
  });
}

function compareNumbers(rowA, rowB, index) {
  const getValue = (row) => {
    const cell = row.children[index];
    const value = cell?.dataset.value ?? '';
    return Number(value) || 0;
  };
  return getValue(rowA) - getValue(rowB);
}

function compareText(rowA, rowB, index) {
  const getValue = (row) =>
    row.children[index]?.innerText.trim().toLowerCase() ?? '';
  return getValue(rowA).localeCompare(getValue(rowB), 'ru');
}

function initQuickFilters() {
  const buttons = document.querySelectorAll('[data-filter-preset]');
  const form = document.getElementById('filters-form');
  if (!buttons.length || !form) return;

  const presets = {
    'top-revenue': { min_revenue: 500000000 },
    'hi-staff': { min_staff: 100 },
    'usn-only': { uses_usn: 'yes' },
  };

  buttons.forEach((button) => {
    button.addEventListener('click', () => {
      const presetName = button.getAttribute('data-filter-preset');
      const config = presets[presetName];
      if (!config) return;

      Object.entries(config).forEach(([field, value]) => {
        const input = form.querySelector(`[name="${field}"]`);
        if (input) {
          input.value = value ?? '';
        }
      });
      form.submit();
    });
  });
}

function initSelectionControls() {
  const form = document.getElementById('report-form');
  if (!form) return;

  const checkboxes = form.querySelectorAll('.row-checkbox');
  const counter = document.getElementById('selected-count');
  const submitBtn = document.getElementById('report-button');
  const accreditationBtn = document.getElementById('accreditation-button');
  const sendBtn = document.getElementById('send-report-button');
  const selectAll = document.getElementById('select-all');
  const csrfTokenInput = form.querySelector(
    'input[name="csrfmiddlewaretoken"]'
  );
  const csrfToken = csrfTokenInput?.value ?? '';
  const defaultAccreditationLabel = accreditationBtn?.textContent ?? '';
  const sendModal = document.getElementById('send-report-modal');
  const sendForm = document.getElementById('send-report-form');
  const sendSummary = document.getElementById('send-report-summary');
  const hiddenInputsContainer = document.getElementById('send-report-hidden-inputs');
  const hasRecipients = sendBtn?.dataset.hasRecipients === 'true';

  const updateState = () => {
    const selected = Array.from(checkboxes).filter((input) => input.checked);
    counter.textContent = `${selected.length} ${pluralize(
      selected.length,
      'компания',
      'компании',
      'компаний'
    )} выбрано`;
    submitBtn.disabled = selected.length === 0;
    if (accreditationBtn) {
      accreditationBtn.disabled = selected.length === 0;
    }
    if (sendBtn) {
      sendBtn.disabled = selected.length === 0 || !hasRecipients;
    }
    if (selectAll) {
      selectAll.indeterminate =
        selected.length > 0 && selected.length < checkboxes.length;
      selectAll.checked = selected.length === checkboxes.length;
    }
  };

  checkboxes.forEach((input) =>
    input.addEventListener('change', () => {
      updateState();
    })
  );

  if (selectAll) {
    selectAll.addEventListener('change', () => {
      checkboxes.forEach((input) => {
        input.checked = selectAll.checked;
      });
      updateState();
    });
  }

  if (accreditationBtn) {
    accreditationBtn.addEventListener('click', () => {
      const inns = Array.from(checkboxes)
        .filter((input) => input.checked)
        .map((input) => input.value);
      if (!inns.length) return;

      accreditationBtn.disabled = true;
      accreditationBtn.textContent = 'Обновляем...';

      fetch(accreditationBtn.dataset.action, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrfToken,
        },
        body: JSON.stringify({ inns }),
      })
        .then((response) => {
          if (!response.ok) {
            throw new Error('Сервис вернул ошибку');
          }
          return response.json();
        })
        .then((data) => {
          if (data.success) {
            accreditationBtn.textContent = 'Готово';
            setTimeout(() => window.location.reload(), 600);
          } else {
            throw new Error(data.message || 'Не удалось обновить статусы');
          }
        })
        .catch((error) => {
          console.error(error);
          accreditationBtn.textContent = 'Ошибка';
          setTimeout(() => {
            accreditationBtn.textContent = defaultAccreditationLabel;
            accreditationBtn.disabled = false;
          }, 1200);
        });
    });
  }

  const closeSendModal = () => {
    if (!sendModal) return;
    sendModal.classList.remove('is-open');
    sendModal.setAttribute('aria-hidden', 'true');
    if (hiddenInputsContainer) {
      hiddenInputsContainer.innerHTML = '';
    }
  };

  const openSendModal = (selected) => {
    if (!sendModal || !sendSummary || !hiddenInputsContainer) return;
    hiddenInputsContainer.innerHTML = '';
    selected.forEach((input) => {
      const hidden = document.createElement('input');
      hidden.type = 'hidden';
      hidden.name = 'company_inn';
      hidden.value = input.value;
      hiddenInputsContainer.appendChild(hidden);
    });
    const names = selected.slice(0, 3).map((input) => {
      const row = input.closest('tr');
      const nameElement = row ? row.querySelector('.company-name strong') : null;
      const nameText = nameElement ? nameElement.textContent.trim() : '';
      return nameText || input.value;
    });
    let preview = 'Компании не выбраны.';
    if (names.length) {
      const rest = selected.length - names.length;
      preview = `${names.join(', ')}${rest > 0 ? ` и ещё ${rest}` : ''}`;
    }
    sendSummary.textContent = `Компаний в отчёте: ${selected.length}. ${preview}`;
    sendModal.classList.add('is-open');
    sendModal.setAttribute('aria-hidden', 'false');
  };

  if (sendBtn && hasRecipients) {
    sendBtn.addEventListener('click', () => {
      const selected = Array.from(checkboxes).filter((input) => input.checked);
      if (!selected.length) return;
      openSendModal(selected);
    });
  }

  if (sendModal) {
    const closers = sendModal.querySelectorAll('[data-modal-close="true"]');
    closers.forEach((btn) =>
      btn.addEventListener('click', () => {
        closeSendModal();
      })
    );
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && sendModal.classList.contains('is-open')) {
        event.preventDefault();
        closeSendModal();
      }
    });
  }

  // Добавляем обработчик для кнопки создания отчёта
  if (submitBtn) {
    form.addEventListener('submit', (e) => {
      const selected = Array.from(checkboxes).filter((input) => input.checked);
      if (selected.length === 0) {
        e.preventDefault();
        return;
      }

      // Показываем индикацию загрузки
      submitBtn.disabled = true;
      const originalText = submitBtn.textContent;
      submitBtn.style.cursor = 'wait';
      submitBtn.textContent = '📄 Формируем отчёт... Пожалуйста подождите';
      
      // Добавляем спиннер загрузки
      if (!submitBtn.querySelector('.spinner')) {
        const spinner = document.createElement('span');
        spinner.className = 'spinner';
        spinner.innerHTML = ' <span style="display: inline-block; width: 14px; height: 14px; border: 2px solid rgba(255,255,255,0.3); border-top-color: white; border-radius: 50%; animation: spin 0.6s linear infinite; margin-left: 8px;"></span>';
        submitBtn.appendChild(spinner);
        
        // Добавляем стили для анимации
        if (!document.getElementById('spinner-styles')) {
          const style = document.createElement('style');
          style.id = 'spinner-styles';
          style.textContent = `
            @keyframes spin { 
              to { transform: rotate(360deg); } 
            }
            .btn-primary:disabled {
              opacity: 0.7;
              cursor: wait;
            }
          `;
          document.head.appendChild(style);
        }
      }
      
      // Показываем уведомление о загрузке
      const loadingMessage = document.createElement('div');
      loadingMessage.id = 'loading-message';
      loadingMessage.style.cssText = 'position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%); background: white; padding: 24px 32px; border-radius: 16px; box-shadow: 0 10px 40px rgba(0,0,0,0.2); z-index: 9999; text-align: center; min-width: 300px;';
      loadingMessage.innerHTML = `
        <div style="font-size: 18px; font-weight: 600; margin-bottom: 16px; color: #10472b;">📄 Формируем отчёт</div>
        <div style="color: #64748b; margin-bottom: 20px;">Готовим Excel-отчёт по выбранным компаниям. Это может занять до минуты.</div>
        <div style="display: inline-block; width: 40px; height: 40px; border: 4px solid #e2e8f0; border-top-color: #10472b; border-radius: 50%; animation: spin 0.8s linear infinite;"></div>
        <div style="margin-top: 16px; font-size: 14px; color: #94a3b8;">Пожалуйста, подождите...</div>
      `;
      document.body.appendChild(loadingMessage);
      
      // Обновляем сообщение через некоторое время
      let messageIndex = 0;
      const messages = [
        'Анализируем выбранные компании...',
        'Сводим финансовые показатели...',
        'Подготавливаем макет отчёта...',
        'Финализируем экспорт...',
      ];
      
      const messageInterval = setInterval(() => {
        if (submitBtn.disabled && loadingMessage.parentNode) {
          messageIndex = (messageIndex + 1) % messages.length;
          loadingMessage.querySelector('div:nth-child(2)').textContent = messages[messageIndex];
        } else {
          clearInterval(messageInterval);
        }
      }, 2000);
      
      // Удаляем сообщение при загрузке страницы (когда форма отправлена)
      window.addEventListener('beforeunload', () => {
        if (loadingMessage.parentNode) {
          loadingMessage.parentNode.removeChild(loadingMessage);
        }
      });
    });
  }

  updateState();
}

function pluralize(value, form1, form2, form5) {
  const abs = Math.abs(value) % 100;
  const remainder = abs % 10;
  if (abs > 10 && abs < 20) return form5;
  if (remainder > 1 && remainder < 5) return form2;
  if (remainder === 1) return form1;
  return form5;
}

function initNotifications() {
  const script = document.getElementById('notifications-data');
  if (!script) return;
  let notifications = [];
  try {
    notifications = JSON.parse(script.textContent);
  } catch (error) {
    console.warn('Не удалось распарсить уведомления', error);
    return;
  }
  if (!notifications.length) return;

  const stack = document.createElement('div');
  stack.className = 'toast-stack';
  document.body.appendChild(stack);

  notifications.forEach((notification, index) => {
    setTimeout(() => {
      const toast = createToast(notification);
      stack.appendChild(toast);
      setTimeout(() => dismissToast(toast), 12000);
    }, index * 250);
  });
}

function createToast(notification) {
  const toast = document.createElement('div');
  toast.className = `toast toast-${notification.type}`;

  const title = document.createElement('h4');
  title.textContent = notification.title;
  toast.appendChild(title);

  const message = document.createElement('p');
  message.textContent = notification.message;
  toast.appendChild(message);

  if (notification.count) {
    const count = document.createElement('small');
    count.textContent = `Затронуто компаний: ${notification.count}`;
    toast.appendChild(count);
  }

  if (notification.companies_preview && notification.companies_preview.length) {
    const preview = document.createElement('small');
    preview.textContent = `Например: ${notification.companies_preview.join(', ')}`;
    toast.appendChild(preview);
  }

  if (notification.download_url) {
    const actions = document.createElement('div');
    actions.className = 'toast-actions';
    const link = document.createElement('a');
    link.href = notification.download_url;
    link.textContent = 'Скачать отчёт';
    link.className = 'btn-link';
    actions.appendChild(link);
    toast.appendChild(actions);
  }

  const closeBtn = document.createElement('button');
  closeBtn.className = 'toast-dismiss';
  closeBtn.setAttribute('aria-label', 'Закрыть уведомление');
  closeBtn.innerHTML = '&times;';
  closeBtn.addEventListener('click', () => dismissToast(toast));
  toast.appendChild(closeBtn);

  return toast;
}

function dismissToast(toast) {
  if (!toast || toast.classList.contains('toast-hidden')) return;
  toast.classList.add('toast-hidden');
  toast.style.opacity = '0';
  setTimeout(() => {
    toast.remove();
    if (!document.querySelector('.toast')) {
      const stack = document.querySelector('.toast-stack');
      stack?.remove();
    }
  }, 200);
}

function initPagination() {
  const paginationLinks = document.querySelectorAll('.pagination .pagination-btn[href]');
  const dataTable = document.querySelector('.data-table');
  
  if (!paginationLinks.length || !dataTable) return;

  // Прокрутка к началу таблицы при загрузке страницы с пагинацией
  if (window.location.search.includes('page=')) {
    setTimeout(() => {
      dataTable.scrollIntoView({ 
        behavior: 'smooth', 
        block: 'start' 
      });
    }, 100);
  }

  paginationLinks.forEach(link => {
    link.addEventListener('click', (e) => {
      // Плавная прокрутка к началу таблицы
      dataTable.scrollIntoView({ 
        behavior: 'smooth', 
        block: 'start' 
      });
      
      // Небольшая задержка для плавности, затем переход
      setTimeout(() => {
        window.location.href = link.href;
      }, 200);
      
      e.preventDefault();
    });
  });
}
