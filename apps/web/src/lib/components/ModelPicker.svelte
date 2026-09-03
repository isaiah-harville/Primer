<script lang="ts">
	import { Cpu, TriangleAlert } from '@lucide/svelte';
	import { DropdownMenu } from '@sivir-ui/svelte';

	interface Props {
		models: { id: string; default: boolean }[];
		/** Empty means the deployment's default. */
		value?: string;
		/**
		 * Why there is no model, when there is none. Null when all is well.
		 *
		 * Carried as a sentence rather than a flag because the causes need
		 * different fixes: an inference endpoint that is down, one that is up
		 * with nothing loaded, and a Chat service that cannot be reached at
		 * all are three different jobs for whoever runs this.
		 */
		problem?: string | null;
	}

	let { models, value = $bindable(''), problem = null }: Props = $props();

	let chosen = $derived(models.find((model) => model.id === value));
	let fallback = $derived(models.find((model) => model.default) ?? models[0]);
	let shown = $derived(chosen ?? fallback);

	//: Whether there is anything to pick between. Most deployments serve one
	//: model, and a menu with a single entry is a control that does nothing.
	let choosable = $derived(models.length > 1);
</script>

<!--
  Always says which model is answering, even when there is no choice to make.

  It used to hide itself entirely whenever a deployment served one model,
  which is the common case - so the usual experience was a chat window that
  never named the thing writing the answers. Which model wrote an answer is a
  fact about the answer, not a preference, and it belongs on screen whether
  or not it can be changed.
-->
{#if shown === undefined}
	<!--
	  No model, and the reason. Not a picker in an error colour: there is
	  nothing to pick, and a control implies otherwise. This used to show the
	  configured default name, which meant an endpoint that was down looked
	  exactly like one that was up.
	-->
	<span
		class="flex items-center gap-2 px-1 py-1.5 text-sm text-error"
		title={problem ?? 'No model is available.'}
	>
		<TriangleAlert size={14} aria-hidden="true" />
		<span class="max-w-[22rem] truncate">No model available</span>
	</span>
{:else if choosable}
	<DropdownMenu.Root>
		<DropdownMenu.Trigger variant="ghost" size="sm" class="text-muted-foreground">
			<Cpu size={14} aria-hidden="true" />
			<span class="max-w-[16rem] truncate font-mono text-xs" title={shown.id}>
				{shown.id}
			</span>
		</DropdownMenu.Trigger>
		<DropdownMenu.Content>
			<DropdownMenu.RadioGroup {value} onValueChange={(next) => (value = next)}>
				{#each models as model (model.id)}
					<DropdownMenu.RadioItem value={model.id}>
						<span class="flex w-full items-center justify-between gap-4">
							<span class="truncate">{model.id}</span>
							{#if model.default}
								<span class="text-xs text-muted-foreground">Default</span>
							{/if}
						</span>
					</DropdownMenu.RadioItem>
				{/each}
			</DropdownMenu.RadioGroup>
		</DropdownMenu.Content>
	</DropdownMenu.Root>
{:else}
	<!--
	  One model: plain text rather than a dead menu, so nothing invites a
	  click that leads nowhere.
	-->
	<span
		class="flex items-center gap-2 px-1 py-1.5 text-sm text-muted-foreground"
		title="Answered by {shown.id}. This deployment serves one model."
	>
		<Cpu size={14} aria-hidden="true" />
		<span class="max-w-[16rem] truncate font-mono text-xs">{shown.id}</span>
	</span>
{/if}
