<script lang="ts">
	import type { IngestionStatus } from '$lib/api/types';
	import { describeStatus } from '$lib/status';

	interface Props {
		status: IngestionStatus;
		detail?: string | null;
	}

	let { status, detail = null }: Props = $props();
	let described = $derived(describeStatus(status, detail));
</script>

<!--
  The status is words first and colour second. Colour alone would be
  invisible to a screen reader and ambiguous to anyone who cannot
  distinguish the shades, and these states differ in what the user should do
  about them, not just in severity.
-->
<span class="status" data-tone={described.tone} data-status={status}>
	<span class="label">{described.label}</span>
	<span class="detail">{described.detail}</span>
</span>

<style>
	.status {
		display: inline-flex;
		flex-direction: column;
		gap: 0.125rem;
	}
	.label {
		font-weight: 600;
	}
	.detail {
		color: #475569;
		font-size: 0.8125rem;
	}
	.status[data-tone='ready'] .label {
		color: #15803d;
	}
	.status[data-tone='problem'] .label {
		color: #b91c1c;
	}
	.status[data-tone='pending'] .label {
		color: #b45309;
	}
</style>
