export function partitionSettled<T>(results: PromiseSettledResult<T>[]) {
  const values: T[] = []
  const errors: unknown[] = []
  results.forEach(result => {
    if (result.status === 'fulfilled') values.push(result.value)
    else errors.push(result.reason)
  })
  return { values, errors }
}

export function filterFulfilledSources<T, U>(sources: T[], results: PromiseSettledResult<U>[]) {
  return sources.filter((_, index) => results[index]?.status === 'fulfilled')
}
