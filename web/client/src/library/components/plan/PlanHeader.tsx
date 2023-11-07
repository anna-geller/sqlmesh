import Banner from '@components/banner/Banner'
import { useStoreContext } from '~/context/context'
import { EnumVariant } from '~/types/enum'
import { Disclosure } from '@headlessui/react'
import { MinusCircleIcon, PlusCircleIcon } from '@heroicons/react/24/solid'

export default function PlanHeader(): JSX.Element {
  const environment = useStoreContext(s => s.environment)

  const shouldShowBannerProdEnv = environment.isInitial && environment.isDefault

  return (
    <div className="flex flex-col w-full">
      <div className="w-full h-full overflow-auto scrollbar scrollbar--vertical px-4 py-2">
        {shouldShowBannerProdEnv && (
          <Banner variant={EnumVariant.Warning}>
            <Disclosure defaultOpen={false}>
              {({ open }) => (
                <>
                  <div className="flex items-center">
                    <Banner.Headline className="w-full mr-2 text-sm !mb-0">
                      Initializing Prod Environment
                    </Banner.Headline>
                    <Disclosure.Button className="flex items-center justify-between rounded-lg text-left text-sm">
                      {open ? (
                        <MinusCircleIcon className="h-6 w-6 text-warning-500" />
                      ) : (
                        <PlusCircleIcon className="h-6 w-6 text-warning-500" />
                      )}
                    </Disclosure.Button>
                  </div>
                  <Disclosure.Panel className="px-4 pb-2 text-sm mt-2">
                    <Banner.Description>
                      Prod will be completely backfilled in order to ensure
                      there are no data gaps. After this is applied, it is
                      recommended to validate further changes in a dev
                      environment before deploying to production.
                    </Banner.Description>
                  </Disclosure.Panel>
                </>
              )}
            </Disclosure>
          </Banner>
        )}
      </div>
    </div>
  )
}
