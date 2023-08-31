import { Outlet } from 'react-router-dom'
import Page from '../root/Page'
import { useStoreProject } from '@context/project'
import SourceList from '@components/sourceList/SourceList'
import { EnumSize, EnumVariant } from '~/types/enum'
import { EnumRoutes } from '~/routes'
import { Button } from '@components/button/Button'
import { Divider } from '@components/divider/Divider'

export default function PageAudits(): JSX.Element {
  const files = useStoreProject(s => s.files)

  const items = Array.from(files.values()).filter(it => it.isSQLMeshAudit)

  return (
    <Page
      sidebar={
        <div className="flex flex-col w-full h-full">
          <SourceList
            by="shortName"
            byName="shortName"
            variant={EnumVariant.Danger}
            to={EnumRoutes.Audits}
            items={items}
            className="h-full"
          />
          <Divider />
          <div className="py-1 px-1 flex justify-end">
            <Button
              size={EnumSize.sm}
              variant={EnumVariant.Neutral}
            >
              Run All
            </Button>
          </div>
        </div>
      }
      content={<Outlet />}
    />
  )
}