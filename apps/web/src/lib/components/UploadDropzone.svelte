<script lang="ts">
	import type { DeploymentCapabilities } from '$lib/api/types';
	import { describeAccepted, rejectionFor } from '$lib/upload';

	interface Props {
		capabilities: DeploymentCapabilities;
		onupload?: (files: File[]) => void;
	}

	let { capabilities, onupload }: Props = $props();

	let dragging = $state(false);
	let errors = $state<string[]>([]);
	let input = $state<HTMLInputElement>();

	function accept(files: FileList | null) {
		if (!files || files.length === 0) return;
		const accepted: File[] = [];
		const rejected: string[] = [];

		for (const file of files) {
			const rejection = rejectionFor(file, capabilities);
			if (rejection) rejected.push(rejection.message);
			else accepted.push(file);
		}

		// Both are reported. Dropping five files and having two rejected
		// silently would look like the upload half-worked.
		errors = rejected;
		if (accepted.length > 0) onupload?.(accepted);
	}

	function onDrop(event: DragEvent) {
		event.preventDefault();
		dragging = false;
		accept(event.dataTransfer?.files ?? null);
	}
</script>

<!--
  A button, not just a drop target. Dragging is a mouse gesture with no
  keyboard equivalent, so the same element opens a file picker on Enter or
  Space and the whole flow works without a pointer.
-->
<div class="dropzone" class:dragging>
	<button
		type="button"
		class="target"
		aria-describedby="upload-hint"
		onclick={() => input?.click()}
		ondragover={(event) => {
			event.preventDefault();
			dragging = true;
		}}
		ondragleave={() => (dragging = false)}
		ondrop={onDrop}
	>
		<strong>Drop files here, or choose files</strong>
	</button>

	<p id="upload-hint" class="hint">
		{describeAccepted(capabilities)} files.
	</p>

	<input
		bind:this={input}
		type="file"
		multiple
		class="visually-hidden"
		accept={capabilities.supported_extensions.join(',')}
		data-testid="file-input"
		onchange={(event) => {
			accept(event.currentTarget.files);
			// Reset, so choosing the same file twice fires a change event
			// both times - re-uploading after a failure is a real case.
			event.currentTarget.value = '';
		}}
	/>

	<!--
	  aria-live, because a rejection is the result of an action the user just
	  took somewhere else on the page. Without it a screen reader user drops a
	  file and hears nothing at all.
	-->
	<div role="alert" aria-live="assertive" class="errors">
		{#each errors as message (message)}
			<p>{message}</p>
		{/each}
	</div>
</div>

<style>
	.dropzone {
		border: 2px dashed #cbd5e1;
		border-radius: 12px;
		padding: 1.5rem;
		text-align: center;
	}
	.dropzone.dragging {
		border-color: #6366f1;
		background: #eef2ff;
	}
	.target {
		background: none;
		border: 0;
		cursor: pointer;
		font: inherit;
		padding: 0.5rem 1rem;
	}
	.hint {
		color: #475569;
		font-size: 0.875rem;
		margin: 0.25rem 0 0;
	}
	.errors p {
		color: #b91c1c;
		font-size: 0.875rem;
		margin: 0.5rem 0 0;
	}
	.visually-hidden {
		position: absolute;
		width: 1px;
		height: 1px;
		overflow: hidden;
		clip: rect(0 0 0 0);
		white-space: nowrap;
	}
</style>
