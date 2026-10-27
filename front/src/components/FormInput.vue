<template>
  <label class="field">
    <span class="field-label">{{ label }}</span>

    <select
      v-if="type === 'select'"
      class="field-control"
      :value="modelValue"
      @change="emit('update:modelValue', $event.target.value)"
    >
      <option value="" disabled>{{ placeholder || `请选择${label}` }}</option>
      <option v-for="option in options" :key="option.value" :value="option.value">
        {{ option.label }}
      </option>
    </select>

    <textarea
      v-else-if="type === 'textarea'"
      class="field-control field-textarea"
      :value="modelValue"
      :placeholder="placeholder"
      :rows="rows"
      @input="emit('update:modelValue', $event.target.value)"
    />

    <input
      v-else
      class="field-control"
      :type="type"
      :value="modelValue"
      :placeholder="placeholder"
      @input="emit('update:modelValue', $event.target.value)"
    />
  </label>
</template>

<script setup>
const emit = defineEmits(['update:modelValue']);

defineProps({
  label: {
    type: String,
    required: true,
  },
  modelValue: {
    type: String,
    default: '',
  },
  type: {
    type: String,
    default: 'text',
  },
  placeholder: {
    type: String,
    default: '',
  },
  options: {
    type: Array,
    default: () => [],
  },
  rows: {
    type: Number,
    default: 4,
  },
});
</script>

<style scoped>
.field {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.field-label {
  color: var(--text-main);
  font-weight: 600;
}

.field-control {
  width: 100%;
  border: 1px solid var(--line-soft);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.84);
  padding: 0.92rem 1rem;
  color: var(--text-main);
  outline: none;
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}

.field-control:focus {
  border-color: rgba(127, 164, 190, 0.55);
  box-shadow: 0 0 0 4px rgba(206, 228, 245, 0.42);
}

.field-textarea {
  resize: vertical;
}
</style>
