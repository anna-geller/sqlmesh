import { useParams } from 'react-router-dom'
import { isNil } from '@utils/index'
import PlanProvider from '@components/plan/context'
import { useStoreContext } from '@context/context'
import Plan from '@components/plan/Plan'
import { EnumRoutes } from '~/routes'
import NotFound from '../root/NotFound'

export default function Content(): JSX.Element {
  const { environmentName } = useParams()

  const environments = useStoreContext(s => s.environments)

  const environment = isNil(environmentName)
    ? undefined
    : Array.from(environments).find(
        environment => environment.name === environmentName,
      )

  return (
    <PlanProvider>
      {isNil(environment) ? (
        <NotFound
          link={EnumRoutes.Plan}
          descritpion={
            isNil(environmentName)
              ? undefined
              : `Model ${environmentName} Does Not Exist`
          }
          message="Back To Docs"
        />
      ) : (
        <Plan
          key={environment.name}
          environment={environment}
        />
      )}
    </PlanProvider>
  )
}
