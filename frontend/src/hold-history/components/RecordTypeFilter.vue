<script setup>
const props = defineProps({
  modelValue: {
    type: Array,
    default: () => ['new'],
  },
  disabled: {
    type: Boolean,
    default: false,
  },
});

const emit = defineEmits(['update:modelValue']);

function toggle(value) {
  const current = props.modelValue || [];
  const idx = current.indexOf(value);
  let next;
  if (idx >= 0) {
    next = current.filter((v) => v !== value);
  } else {
    next = [...current, value];
  }
  if (next.length === 0) {
    return;
  }
  emit('update:modelValue', next);
}

function isChecked(value) {
  return (props.modelValue || []).includes(value);
}
</script>

<template>
  <section class="record-type-filter">
    <span class="filter-label">Record Type</span>
    <div class="checkbox-group">
      <label class="checkbox-option" :class="{ active: isChecked('new') }">
        <input type="checkbox" :checked="isChecked('new')" :disabled="disabled" @change="toggle('new')" />
        <span>New Hold</span>
      </label>
      <label class="checkbox-option" :class="{ active: isChecked('on_hold') }">
        <input type="checkbox" :checked="isChecked('on_hold')" :disabled="disabled" @change="toggle('on_hold')" />
        <span>On Hold</span>
      </label>
      <label class="checkbox-option" :class="{ active: isChecked('released') }">
        <input type="checkbox" :checked="isChecked('released')" :disabled="disabled" @change="toggle('released')" />
        <span>Released</span>
      </label>
    </div>
  </section>
</template>
