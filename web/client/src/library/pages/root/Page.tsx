import {
  FolderIcon,
  DocumentTextIcon,
  DocumentCheckIcon,
  ShieldCheckIcon,
  ExclamationTriangleIcon,
  PlayCircleIcon,
} from '@heroicons/react/24/solid'
import clsx from 'clsx'
import {
  FolderIcon as OutlineFolderIcon,
  DocumentTextIcon as OutlineDocumentTextIcon,
  ExclamationTriangleIcon as OutlineExclamationTriangleIcon,
  DocumentCheckIcon as OutlineDocumentCheckIcon,
  ShieldCheckIcon as OutlineShieldCheckIcon,
  PlayCircleIcon as OutlinePlayCircleIcon,
} from '@heroicons/react/24/outline'
import { Link, NavLink, useLocation } from 'react-router-dom'
import { EnumRoutes } from '~/routes'
import { useStoreProject } from '@context/project'
import { Divider } from '@components/divider/Divider'
import SplitPane from '@components/splitPane/SplitPane'
import { useStoreContext } from '@context/context'
import { useIDE } from '../ide/context'
import { useStorePlan } from '@context/plan'
import { useApiPlanRun } from '@api/index'
import { isFalse } from '@utils/index'
import { PlanChanges, SelectEnvironemnt } from '../ide/RunPlan'
import { EnumSize, EnumVariant } from '~/types/enum'
import { type ModelPlanOverviewTracker } from '@models/tracker-plan-overview'
import { type ModelPlanApplyTracker } from '@models/tracker-plan-apply'
import Spinner from '@components/logo/Spinner'

export default function Page({
  sidebar,
  content,
}: {
  sidebar: React.ReactNode
  content: React.ReactNode
}): JSX.Element {
  const location = useLocation()
  const { errors } = useIDE()

  const models = useStoreContext(s => s.models)
  const splitPaneSizes = useStoreContext(s => s.splitPaneSizes)
  const setSplitPaneSizes = useStoreContext(s => s.setSplitPaneSizes)

  const project = useStoreProject(s => s.project)

  const modelsCount = Array.from(new Set(models.values())).length

  return (
    <SplitPane
      sizes={splitPaneSizes}
      minSize={[0, 0]}
      snapOffset={0}
      className="flex w-full h-full overflow-hidden"
      onDragEnd={setSplitPaneSizes}
    >
      <div className="flex flex-col h-full overflow-hidden">
        <div className="px-1 flex max-h-8 w-full items-center relative">
          <div className="px-2">
            <h3 className="flex items-center h-8 font-bold text-primary-500 text-sm">
              <span className="inline-block">/</span>
              {project?.name}
            </h3>
          </div>
          <EnvironmentDetails />
        </div>
        <Divider />
        <div className="px-1 flex max-h-8 w-full items-center relative">
          <div className="h-8 flex w-full items-center justify-center px-1 py-0.5 text-neutral-500">
            <Link
              title="File Explorer"
              to={EnumRoutes.Editor}
              className={clsx(
                'mx-1 py-1 flex items-center rounded-full',
                location.pathname.startsWith(EnumRoutes.Editor) &&
                  'px-2 bg-neutral-10',
              )}
            >
              {location.pathname.startsWith(EnumRoutes.Editor) ? (
                <FolderIcon className="w-4" />
              ) : (
                <OutlineFolderIcon className="w-4" />
              )}
            </Link>
            <Link
              title="Docs"
              to={EnumRoutes.Docs}
              className={clsx(
                'mx-1 py-1 flex items-center rounded-full',
                location.pathname.startsWith(EnumRoutes.Docs) &&
                  'px-2 bg-neutral-10',
              )}
            >
              {location.pathname.startsWith(EnumRoutes.Docs) ? (
                <DocumentTextIcon className="w-4" />
              ) : (
                <OutlineDocumentTextIcon className="w-4" />
              )}
              <span className="block ml-1 text-xs">{modelsCount}</span>
            </Link>
            <NavLink
              title="Errors"
              to={errors.size === 0 ? '' : EnumRoutes.Errors}
              className={clsx(
                'mx-1 py-1 flex items-center rounded-full',
                errors.size === 0
                  ? 'opacity-50 cursor-not-allowed'
                  : 'px-2 bg-danger-10 text-danger-500',
              )}
            >
              {({ isActive }) => (
                <>
                  {isActive ? (
                    <ExclamationTriangleIcon className="w-4" />
                  ) : (
                    <OutlineExclamationTriangleIcon className="w-4" />
                  )}
                  {errors.size > 0 && (
                    <span className="block ml-1 text-xs">{errors.size}</span>
                  )}
                </>
              )}
            </NavLink>
            <Link
              title="Tests"
              to={EnumRoutes.Tests}
              className={clsx(
                'mx-0.5 py-1 flex items-center rounded-full',
                location.pathname.startsWith(EnumRoutes.Tests) &&
                  'px-2 bg-neutral-10',
              )}
            >
              {location.pathname.startsWith(EnumRoutes.Tests) ? (
                <DocumentCheckIcon className="w-4" />
              ) : (
                <OutlineDocumentCheckIcon className="w-4" />
              )}
            </Link>
            <Link
              title="Audits"
              to={EnumRoutes.Audits}
              className={clsx(
                'mx-1 py-1 flex items-center rounded-full',
                location.pathname.startsWith(EnumRoutes.Audits) &&
                  'px-2 bg-neutral-10',
              )}
            >
              {location.pathname.startsWith(EnumRoutes.Audits) ? (
                <ShieldCheckIcon className="w-4" />
              ) : (
                <OutlineShieldCheckIcon className="w-4" />
              )}
            </Link>
            <NavLink
              title="Plan"
              to={EnumRoutes.Plan}
              className="mx-1 py-0.5 px-2 flex items-center rounded-full bg-success-10"
            >
              <b className="block mx-1 text-xs text-success-500">Plan</b>
              {location.pathname.startsWith(EnumRoutes.Plan) ? (
                <PlayCircleIcon className="text-success-500 w-5" />
              ) : (
                <OutlinePlayCircleIcon className="text-success-500 w-5" />
              )}
            </NavLink>
          </div>
        </div>
        <Divider />
        <div className="w-full h-full">{sidebar}</div>
      </div>
      <div className="w-full h-full">{content}</div>
    </SplitPane>
  )
}

function EnvironmentDetails(): JSX.Element {
  const environment = useStoreContext(s => s.environment)

  const planOverview = useStorePlan(s => s.planOverview)
  const planApply = useStorePlan(s => s.planApply)

  const hasSynchronizedEnvironments = useStoreContext(
    s => s.hasSynchronizedEnvironments,
  )

  const { isFetching } = useApiPlanRun(environment.name, {
    planOptions: { skip_tests: true, include_unmodified: true },
  })

  const showSelectEnvironmentButton =
    (isFalse(environment.isDefault) || hasSynchronizedEnvironments()) &&
    (isFalse(environment.isDefault) || isFalse(environment.isInitial))

  return (
    <div className="h-8 flex w-full items-center justify-end py-0.5 text-neutral-500">
      <div className="px-2 flex items-center">
        <PlanStatus className="mr-2" />
        <PlanChanges
          environment={environment}
          isRunningPlanOverview={isFetching || planOverview.isRunning}
          isRunningPlanApply={planApply.isRunning}
        />
      </div>
      {showSelectEnvironmentButton && (
        <SelectEnvironemnt
          className="border-none h-6 !m-0"
          size={EnumSize.sm}
          onSelect={env => {
            // setPlan(undefined)
            // setHasChanges(false)
          }}
        />
      )}
    </div>
  )
}

function PlanStatus({ className }: { className?: string }): JSX.Element {
  const planOverview = useStorePlan(s => s.planOverview)
  const planApply = useStorePlan(s => s.planApply)

  const isRunning = planApply.isRunning || planOverview.isRunning

  return isRunning ? (
    <span
      className={clsx(
        'flex items-center ml-2 py-0.5 px-3 bg-neutral-10 rounded-full',
        className,
      )}
    >
      {isRunning && (
        <Spinner
          className="w-3 h-3 mr-2 !fill-neutral-50"
          variant={EnumVariant.Neutral}
        />
      )}
      <span className="inline-block whitespace-nowrap text-xs text-neutral-500">
        {getPlanStatus(planOverview, planApply)}
      </span>
    </span>
  ) : (
    <></>
  )
}

function getPlanStatus(
  planOverview: ModelPlanOverviewTracker,
  planApply: ModelPlanApplyTracker,
): string {
  if (planApply.isRunning) return 'Applying Plan...'
  if (planOverview.isRunning) return 'Getting Changes...'

  return 'Latest'
}
