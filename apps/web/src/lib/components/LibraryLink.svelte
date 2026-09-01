<script lang="ts">
	import { Library, Link2Off } from '@lucide/svelte';
	import { DropdownMenu } from '@sivir-ui/svelte';
	import type { LibrarySummary } from '$lib/api/types';

	interface Props {
		libraries: LibrarySummary[];
		/** Empty means no library: the model answers on its own. */
		value?: string;
	}

	let { libraries, value = $bindable('') }: Props = $props();

	let linked = $derived(libraries.find((library) => library.id === value));
</script>

<!--
  Under the composer rather than beside the title, because it is part of
  asking rather than part of the page: whether this question will be answered
  from your documents is decided in the same place you type it.

  Unlinked is drawn in the error colour and named as a state, not left blank.
  An answer with no library is a different kind of answer, and the moment to
  notice that is before asking rather than after reading one.
-->
<DropdownMenu.Root>
	<DropdownMenu.Trigger
		variant="ghost"
		size="sm"
		class={linked
			? 'text-muted-foreground'
			: 'text-error hover:text-error border border-error/40 bg-error/5'}
	>
		{#if linked}
			<Library size={14} aria-hidden="true" />
			<span class="max-w-[16rem] truncate" title={linked.name}>{linked.name}</span>
		{:else}
			<Link2Off size={14} aria-hidden="true" />
			<span>No library linked</span>
		{/if}
	</DropdownMenu.Trigger>

	<DropdownMenu.Content>
		<DropdownMenu.RadioGroup {value} onValueChange={(next) => (value = next)}>
			<DropdownMenu.RadioItem value="">
				<span class="flex items-center gap-2">
					<Link2Off size={14} aria-hidden="true" />
					No library
				</span>
			</DropdownMenu.RadioItem>

			{#each libraries as library (library.id)}
				<DropdownMenu.RadioItem value={library.id}>
					<span class="flex w-full items-center justify-between gap-4">
						<span class="truncate">{library.name}</span>
						<span class="font-mono text-[11px] text-muted-foreground">
							{library.document_count}
						</span>
					</span>
				</DropdownMenu.RadioItem>
			{/each}
		</DropdownMenu.RadioGroup>

		{#if libraries.length === 0}
			<!--
			  Said here rather than by hiding the control: someone looking for
			  their libraries needs to know there are none, not find an empty
			  menu and wonder whether it failed to load.
			-->
			<p class="px-2.5 py-2 text-xs text-muted-foreground">
				No libraries yet. Answers will come from the model alone.
			</p>
		{/if}
	</DropdownMenu.Content>
</DropdownMenu.Root>
