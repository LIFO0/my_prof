document.addEventListener('DOMContentLoaded', () => {
  initLiveSearch();
  initSortableTable();
  initQuickFilters();
  initSelectionControls();
});

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
      const direction =
        sortState.index === index ? sortState.direction * -1 : 1;
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
  const selectAll = document.getElementById('select-all');
  const csrfTokenInput = form.querySelector(
    'input[name="csrfmiddlewaretoken"]'
  );
  const csrfToken = csrfTokenInput?.value ?? '';
  const defaultAccreditationLabel = accreditationBtn?.textContent ?? '';

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
