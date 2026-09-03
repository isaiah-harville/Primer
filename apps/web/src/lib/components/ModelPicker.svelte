<script lang="ts">
	import { Cpu } from '@lucide/svelte';
	import { DropdownMenu } from '@sivir-ui/svelte';

	interface Props {
		models: { id: string; default: boolean }[];
		/** Empty means the deployment's default. */
		value?: string;
		//: True when Chat could not be reached for the list, as opposed to a
		//: deployment that was reached and genuinely offers only one model.
		//: The two look identical in `models` alone - both empty or
		//: single-entry - so the caller has to say which one this is.
		unavailable?: boolean;
	}

	let { models, value = $bindable(''), unavailable = false }: Props = $props();

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

  With one model it is plain text rather than a dead menu, so nothing invites
  a click that leads nowhere.
-->
{#if choosable}
	<DropdownMenu.Root>
		<DropdownMenu.Trigger
			variant="ghost"
			size="sm"
			class={unavailable ? 'text-error' : 'text-muted-foreground'}
		>
			<Cpu size={14} aria-hidden="true" />
			<span class="max-w-[16rem] truncate font-mono text-xs" title={shown?.id}>
				{shown?.id}
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
	<span
		class="flex items-center gap-2 px-1 py-1.5 text-sm
			{unavailable ? 'text-error' : 'text-muted-foreground'}"
		title={unavailable
			? 'The model list could not be fetched. Questions are still answered by this deployment’s default model.'
			: `Answered by ${shown?.id}. This deployment serves one model.`}
	>
		<Cpu size={14} aria-hidden="true" />
		<!--
		  Named where a name is known. Unreachable and unnamed are different
		  states and are worded differently: one is a deployment offering its
		  single model, the other is Chat not answering, and a person watching
		  a slow answer needs to be able to tell which they are looking at.
		-->
		<span class="max-w-[16rem] truncate font-mono text-xs">
			{shown?.id ?? (unavailable ? 'Model list unavailable' : 'Default model')}
		</span>
	</span>
{/if}
