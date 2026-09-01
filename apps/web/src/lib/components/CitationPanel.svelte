<script lang="ts">
	import { Badge, Card, Sheet } from '@sivir-ui/svelte';
	import type { Citation } from '$lib/api/types';
	import { describeCitation } from '$lib/export/markdown';

	interface Props {
		citations: Citation[];
		filenames?: Record<string, string>;
		/** Bound, so the parent opens it and Sheet closes it. */
		open?: boolean;
	}

	let { citations, filenames = {}, open = $bindable(false) }: Props = $props();

	function nameFor(citation: Citation): string | undefined {
		return filenames[citation.document_version_id] ?? filenames[citation.document_id];
	}
</script>

<!--
  A panel, not a tooltip: a reader checking a citation wants to compare the
  quoted passage against the claim, which means both need to stay on screen.
  Sheet is focus-trapped and closes on Escape, so it is reachable and
  escapable from the keyboard.
-->
<Sheet.Root bind:open>
	<Sheet.Content side="right" class="w-full max-w-md">
		<Sheet.Header>
			<Sheet.Title>Sources</Sheet.Title>
			<Sheet.Description>
				The passages this answer was drawn from, in the order they were cited.
			</Sheet.Description>
		</Sheet.Header>

		<div class="flex flex-col gap-3 overflow-y-auto p-4">
			{#each citations as citation, index (citation.chunk_id)}
				<Card.Root>
					<Card.Header>
						<div class="flex items-center gap-2">
							<Badge variant="secondary">{index + 1}</Badge>
							<span class="text-sm font-medium">
								{describeCitation(citation, nameFor(citation))}
							</span>
						</div>
					</Card.Header>
					{#if citation.excerpt}
						<Card.Content>
							<!--
							  The document's own words, quoted. Never a storage
							  key: how the deployment stores a file is not part
							  of the citation, and showing it would leak layout.
							-->
							<blockquote class="border-l-2 border-border pl-3 text-sm text-muted-foreground">
								{citation.excerpt}
							</blockquote>
						</Card.Content>
					{/if}
				</Card.Root>
			{/each}
		</div>
	</Sheet.Content>
</Sheet.Root>
