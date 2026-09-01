<script lang="ts">
	import { Badge } from '@sivir-ui/svelte';
	import type { IngestionStatus } from '$lib/api/types';
	import { describeStatus } from '$lib/status';

	interface Props {
		status: IngestionStatus;
		detail?: string | null;
	}

	let { status, detail = null }: Props = $props();
	let described = $derived(describeStatus(status, detail));

	const variants = {
		ready: 'success',
		problem: 'destructive',
		pending: 'warning'
	} as const;
</script>

<div class="flex flex-col items-start gap-1">
	<Badge variant={variants[described.tone]}>{described.label}</Badge>
	<span class="text-xs text-muted-foreground">{described.detail}</span>
</div>
