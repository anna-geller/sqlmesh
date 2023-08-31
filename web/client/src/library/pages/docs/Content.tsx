import Documentation from '@components/documentation/Documentation'
import ModelLineage from '@components/graph/ModelLineage'
import SplitPane from '@components/splitPane/SplitPane'
import { useStoreContext } from '@context/context'
import { useNavigate, useParams } from 'react-router-dom'
import NotFound from '../root/NotFound'
import { EnumRoutes } from '~/routes'
import { ModelSQLMeshModel } from '@models/sqlmesh-model'
import LineageFlowProvider from '@components/graph/context'
import { type ErrorIDE } from '../ide/context'
import { isNil, isNotNil } from '@utils/index'
import { useEffect } from 'react'
import { useStoreProject } from '@context/project'

export default function Content(): JSX.Element {
  const { modelName } = useParams()
  const navigate = useNavigate()

  const models = useStoreContext(s => s.models)
  const setLastActiveModel = useStoreContext(s => s.setLastActiveModel)

  const files = useStoreProject(s => s.files)
  const setSelectedFile = useStoreProject(s => s.setSelectedFile)

  const model = isNil(modelName)
    ? undefined
    : models.get(ModelSQLMeshModel.decodeName(modelName))

  useEffect(() => {
    if (isNotNil(model)) {
      setLastActiveModel(model)

      const file = files.get(model.path)

      if (isNil(file)) return

      setSelectedFile(file)
    }
  }, [model])

  function handleClickModel(modelName: string): void {
    const model = models.get(modelName)

    if (isNil(model)) return

    navigate(
      EnumRoutes.IdeDocsModels + '/' + ModelSQLMeshModel.encodeName(model.name),
    )
  }

  function handleError(error: ErrorIDE): void {
    console.log(error?.message)
  }

  return (
    <div className="flex overflow-auto w-full h-full">
      {isNil(model) ? (
        <NotFound
          link={EnumRoutes.IdeDocs}
          descritpion={
            isNil(modelName) ? undefined : `Model ${modelName} Does Not Exist`
          }
          message="Back To Docs"
        />
      ) : (
        <LineageFlowProvider
          handleClickModel={handleClickModel}
          handleError={handleError}
        >
          <SplitPane
            className="flex h-full w-full"
            sizes={[50, 50]}
            minSize={0}
            snapOffset={0}
          >
            <div className="flex flex-col h-full round">
              <Documentation
                model={model}
                withQuery={model.type === 'sql'}
              />
            </div>
            <div className="flex flex-col h-full px-2">
              <ModelLineage
                model={model}
                key={model.id}
                fingerprint={model.id}
              />
            </div>
          </SplitPane>
        </LineageFlowProvider>
      )}
    </div>
  )
}
