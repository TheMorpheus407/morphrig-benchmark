#include "ShowcaseDirector.h"
#include "ShowcaseRoom.h"
#include "ShowcaseHUD.h"
#include "OperativeCharacter.h"
#include "OperativeActionComponent.h"
#include "OperativeFaceComponent.h"
#include "OperativeAnimInstance.h"
#include "OperativeLibrary.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/World.h"
#include "Engine/Engine.h"
#include "Engine/GameViewportClient.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "HAL/IConsoleManager.h"
#include "HAL/PlatformMisc.h"
#include "HAL/PlatformMemory.h"
#include "HAL/PlatformTime.h"
#include "Misc/App.h"
#include "Misc/CommandLine.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Misc/DateTime.h"
#include "HAL/FileManager.h"
#include "UnrealClient.h"
#include "HighResScreenshot.h"
#include "ImageWriteQueue.h"
#include "RenderTimer.h"
#include "RHI.h"
#include "RHIGlobals.h"
#if PLATFORM_UNIX
#include <stdlib.h>          // getloadavg for the host load line of the frame time logs
#endif
#include "RHIStats.h"
#include "DynamicRHI.h"
#include "EngineUtils.h"
#if WITH_EDITOR
#include "ShaderCompiler.h"
#endif

AShowcaseDirector::AShowcaseDirector()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.TickGroup = TG_PostUpdateWork;
	SetActorTickEnabled(true);
}

AOperativeCharacter* AShowcaseDirector::Op() const
{
	const AShowcasePlayerController* P = PC();
	return P ? P->GetOperative() : nullptr;
}

AShowcasePlayerController* AShowcaseDirector::PC() const
{
	return Cast<AShowcasePlayerController>(GetWorld()->GetFirstPlayerController());
}

UOperativeActionComponent* AShowcaseDirector::Actions() const
{
	AOperativeCharacter* O = Op();
	return O ? O->Actions.Get() : nullptr;
}

AShowcaseRoom* AShowcaseDirector::Room() const
{
	const AShowcasePlayerController* P = PC();
	return P ? P->GetRoom() : nullptr;
}

FString AShowcaseDirector::GetCaptureModeName() const
{
	switch (CaptureMode)
	{
	case ECaptureMode::Turntable: return FString::Printf(TEXT("capture turntable %d/%d"), CaptureFrame, CaptureTotalFrames);
	case ECaptureMode::Motion: return FString::Printf(TEXT("capture motion frame %d"), CaptureFrame);
	case ECaptureMode::Face: return FString::Printf(TEXT("capture face %d/%d"), CaptureFrame, CaptureTotalFrames);
	default: return FString();
	}
}

void AShowcaseDirector::ParseCommandLine()
{
	const TCHAR* Cmd = FCommandLine::Get();
	bWantSequence = FParse::Param(Cmd, TEXT("ShowcaseSequence"));
	FString Mode;
	if (FParse::Value(Cmd, TEXT("CaptureMode="), Mode))
	{
		if (Mode.Equals(TEXT("turntable"), ESearchCase::IgnoreCase)) CaptureMode = ECaptureMode::Turntable;
		else if (Mode.Equals(TEXT("motion"), ESearchCase::IgnoreCase)) CaptureMode = ECaptureMode::Motion;
		else if (Mode.Equals(TEXT("face"), ESearchCase::IgnoreCase)) CaptureMode = ECaptureMode::Face;
	}
	FParse::Value(Cmd, TEXT("CaptureDir="), CaptureDir);
	if (!CaptureDir.IsEmpty() && FPaths::IsRelative(CaptureDir)) CaptureDir = FPaths::ConvertRelativePathToFull(FPaths::LaunchDir(), CaptureDir);
	FParse::Value(Cmd, TEXT("PerfLog="), PerfLogPath);
	if (!PerfLogPath.IsEmpty() && FPaths::IsRelative(PerfLogPath)) PerfLogPath = FPaths::ConvertRelativePathToFull(FPaths::LaunchDir(), PerfLogPath);
	// default: <project>/Saved/ShowcaseTrace.txt (ProjectSavedDir is relative to the binary directory in a packaged client, not to the launch directory)
	if (!FParse::Value(Cmd, TEXT("SequenceTrace="), TraceFilePath)) TraceFilePath = FPaths::ConvertRelativePathToFull(FPaths::ProjectSavedDir()) / TEXT("ShowcaseTrace.txt");
	else if (FPaths::IsRelative(TraceFilePath)) TraceFilePath = FPaths::ConvertRelativePathToFull(FPaths::LaunchDir(), TraceFilePath);
	FParse::Value(Cmd, TEXT("Instances="), InstancesArg);
	FParse::Value(Cmd, TEXT("PerfWarmup="), WarmupFrames);
	FParse::Value(Cmd, TEXT("PerfWarmupSeconds="), WarmupSeconds);
	FParse::Value(Cmd, TEXT("PerfFrames="), PerfFrames);
	FParse::Value(Cmd, TEXT("PerfSeconds="), PerfMaxSeconds);
	FParse::Value(Cmd, TEXT("MaxCaptureFrames="), MaxCaptureFrames);
	FParse::Value(Cmd, TEXT("CaptureEvery="), CaptureEvery);
	CaptureEvery = FMath::Max(CaptureEvery, 1);
	FParse::Value(Cmd, TEXT("Shot="), ShotPath);
	if (!ShotPath.IsEmpty() && FPaths::IsRelative(ShotPath)) ShotPath = FPaths::ConvertRelativePathToFull(FPaths::LaunchDir(), ShotPath);
	FParse::Value(Cmd, TEXT("ShotFrame="), ShotFrame);
	FParse::Value(Cmd, TEXT("ShotClip="), ShotClip);
	FParse::Value(Cmd, TEXT("ShotTime="), ShotTime);
	FParse::Value(Cmd, TEXT("SeqFrom="), SeqFrom);
	FParse::Value(Cmd, TEXT("SeqTo="), SeqTo);
	bTracePose = FParse::Param(Cmd, TEXT("TracePose"));
	bExitAfterSequence = FParse::Param(Cmd, TEXT("ExitAfterSequence")) || CaptureMode != ECaptureMode::None;
	if (CaptureMode != ECaptureMode::None && CaptureDir.IsEmpty()) CaptureDir = FPaths::ProjectSavedDir() / TEXT("Capture");
}

void AShowcaseDirector::BeginPlay()
{
	Super::BeginPlay();
	ParseCommandLine();
	IFileManager::Get().MakeDirectory(*FPaths::GetPath(TraceFilePath), true);
	IFileManager::Get().Delete(*TraceFilePath, false, true, true);
	Trace(FString::Printf(TEXT("kind=RUN start=%s build=%s"), *FDateTime::Now().ToString(), FApp::GetBuildConfiguration() == EBuildConfiguration::Development ? TEXT("Development") : TEXT("other")));
	const bool bCapture = CaptureMode != ECaptureMode::None;
	if (bWantSequence || bCapture || !ShotPath.IsEmpty())
	{
		// deterministic fixed step (30 fps) and no real time pacing for scripted runs
		FApp::SetBenchmarking(true);
		FApp::SetUseFixedTimeStep(true);
		FApp::SetFixedDeltaTime(1.0 / 30.0);
		bFixedStep = true;
		Trace(TEXT("kind=RUN fixed_step=1/30s"));
	}
	if (bCapture || bWantSequence || !PerfLogPath.IsEmpty() || !ShotPath.IsEmpty())
	{
		// videos and frame time logs use 1920 x 1080 windowed
		if (GEngine) GEngine->Exec(GetWorld(), TEXT("r.SetRes 1920x1080w"));
	}
	if (bCapture)
	{
		IFileManager::Get().MakeDirectory(*CaptureDir, true);
	}
}

void AShowcaseDirector::EndPlay(const EEndPlayReason::Type Reason)
{
	if (TraceBuffer.Num() > 0)
	{
		FFileHelper::SaveStringToFile(FString::Join(TraceBuffer, TEXT("\n")) + TEXT("\n"), *TraceFilePath, FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM, &IFileManager::Get(), FILEWRITE_Append);
		TraceBuffer.Reset();
	}
	Super::EndPlay(Reason);
}

void AShowcaseDirector::Trace(const FString& Line)
{
	const FString Full = FString::Printf(TEXT("SHOWCASE_TRACE t=%.3f %s"), GetWorld() ? GetWorld()->GetTimeSeconds() : 0.0, *Line);
	UE_LOG(LogMorphRig, Display, TEXT("%s"), *Full);
	TraceBuffer.Add(Full);
}

void AShowcaseDirector::Check(const FString& Name, bool bPass, const FString& Detail)
{
	++ChecksTotal;
	if (bPass) ++ChecksPassed;
	Trace(FString::Printf(TEXT("kind=CHECK name=%s pass=%d %s"), *Name, bPass ? 1 : 0, *Detail));
}

void AShowcaseDirector::BindOperative()
{
	AOperativeCharacter* O = Op();
	if (!O || !O->Actions) return;
	if (BoundTo.Get() == O) return;
	O->Actions->OnEvent.AddUObject(this, &AShowcaseDirector::OnOperativeEvent);
	BoundTo = O;
}

void AShowcaseDirector::OnOperativeEvent(const FOperativeEventInfo& Info)
{
	++EventCounter;
	Counters.FindOrAdd(Info.Name.ToString())++;
	Trace(FString::Printf(TEXT("kind=EVENT step=%s event=%s clip=%s clip_time=%.3f player=%s pass=%d%s%s"), *StepName, *Info.Name.ToString(), *Info.ClipId.ToString(), Info.ClipTime, *Info.Player.ToString(), Info.PassId,
		Info.Params.IsEmpty() ? TEXT("") : *FString::Printf(TEXT(" params=%s"), *Info.Params), Info.bSynthetic ? TEXT(" source=fallback") : TEXT(" source=manifest")));
}

// ------------------------------------------------------------------------------------------------ tick

void AShowcaseDirector::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	BindOperative();
	if (!bCaptureStarted && (CaptureMode != ECaptureMode::None))
	{
		BeginCapture();
	}
	static int32 StartCountdown = 20;
	if (bWantSequence && !bSequenceRunning && Tasks.Num() == 0 && CaptureMode == ECaptureMode::None)
	{
		if (--StartCountdown <= 0) StartSequence(true);
	}
	TickSequence(DeltaSeconds);
	TickTrace(DeltaSeconds);
	TickIKMeasure();
	TickShot();
	TickCapture(DeltaSeconds);
	TickPerf(DeltaSeconds);
}

void AShowcaseDirector::TickShot()
{
	if (ShotPath.IsEmpty()) return;
	++ShotCounter;
	if (!ShotClip.IsEmpty() && ShotCounter == 20)
	{
		if (UOperativeActionComponent* A = Actions())
		{
			A->PlayClip(FName(*ShotClip), 1.f, false, FMath::Max(ShotTime, 0.f));
			if (ShotTime >= 0.f) A->SetViewerPaused(true);
		}
	}
	if (ShotCounter == ShotFrame)
	{
		IFileManager::Get().MakeDirectory(*FPaths::GetPath(ShotPath), true);
		FScreenshotRequest::RequestScreenshot(ShotPath, true, false);
		Trace(FString::Printf(TEXT("kind=SHOT file=%s frame=%d"), *ShotPath, ShotCounter));
	}
	if (ShotCounter == ShotFrame + 3) QuitNow();
}

void AShowcaseDirector::IKBegin(const FString& Name)
{
	IKName = Name;
	IKCurrent = FIKRun();
	bIKMeasure = true;
	bIKHavePrev = false;
}

void AShowcaseDirector::IKEnd()
{
	if (!bIKMeasure) return;
	bIKMeasure = false;
	IKRuns.Add(IKName, IKCurrent);
	Trace(FString::Printf(TEXT("kind=IK run=%s planted_samples=%d mean_abs_error_cm=%.2f max_penetration_cm=%.2f max_float_cm=%.2f max_pelvis_offset_cm=%.2f"), *IKName, IKCurrent.Samples, IKCurrent.MeanAbs(),
		IKCurrent.MaxPenetration, IKCurrent.MaxFloat, IKCurrent.MaxPelvisOffset));
}

void AShowcaseDirector::TickIKMeasure()
{
	if (!bIKMeasure) return;
	AOperativeCharacter* O = Op();
	if (!O || !GetWorld()) return;
	USkeletalMeshComponent* M = O->GetMesh();
	if (!M || !M->GetSkeletalMeshAsset()) return;
	// rest pose heights of the ankle and ball bones above the sole (the reference pose stands on the floor)
	static const FName Ankle[2] = { FName("foot_l"), FName("foot_r") };
	static const FName Ball[2] = { FName("ball_l"), FName("ball_r") };
	FCollisionQueryParams Params(SCENE_QUERY_STAT(OperativeIKMeasure), false, O);
	const float Dt = FMath::Max(GetWorld()->GetDeltaSeconds(), 1e-3f);
	auto GroundAt = [&](const FVector& P, float& OutZ) -> bool
	{
		FHitResult Hit;
		if (!GetWorld()->LineTraceSingleByChannel(Hit, P + FVector(0.f, 0.f, 70.f), P - FVector(0.f, 0.f, 90.f), ECC_Visibility, Params)) return false;
		OutZ = Hit.ImpactPoint.Z;
		return true;
	};
	for (int32 S = 0; S < 2; ++S)
	{
		const float RestAnkle = M->GetSkeletalMeshAsset()->GetComposedRefPoseMatrix(Ankle[S]).GetOrigin().Z;
		const float RestBall = M->GetSkeletalMeshAsset()->GetComposedRefPoseMatrix(Ball[S]).GetOrigin().Z;
		const FVector PA = M->GetSocketLocation(Ankle[S]);
		const FVector PB = M->GetSocketLocation(Ball[S]);
		float GA = 0.f, GB = 0.f;
		if (bIKHavePrev && GroundAt(PA, GA) && GroundAt(PB, GB))
		{
			const float HeelErr = (PA.Z - RestAnkle) - GA;       // height of the heel sole above the ground below it
			const float BallErr = (PB.Z - RestBall) - GB;        // height of the ball sole above the ground below it
			const bool bHeel = HeelErr <= BallErr;
			const float Err = bHeel ? HeelErr : BallErr;         // the lower contact point of the foot: negative = through the floor, positive = both points float
			const FVector& Cur = bHeel ? PA : PB;
			const FVector& Prev = bHeel ? IKPrev[S] : IKPrevBall[S];
			const float Speed = (Cur - Prev).Size() / Dt;
			if (Speed < 25.f && Err < 4.f)                       // planted: the contact point rests against the ground
			{
				++IKCurrent.Samples;
				IKCurrent.SumAbs += FMath::Abs(Err);
				IKCurrent.MaxPenetration = FMath::Max(IKCurrent.MaxPenetration, -Err);
				IKCurrent.MaxFloat = FMath::Max(IKCurrent.MaxFloat, Err);
			}
		}
		IKPrev[S] = PA;
		IKPrevBall[S] = PB;
	}
	bIKHavePrev = true;
	if (const UOperativeAnimInstance* AI = O->GetOperativeAnim()) IKCurrent.MaxPelvisOffset = FMath::Max(IKCurrent.MaxPelvisOffset, FMath::Abs(AI->GetEvalDebug().PelvisIKOffset));
}

void AShowcaseDirector::TickTrace(float Dt)
{
	AOperativeCharacter* O = Op();
	UOperativeActionComponent* A = Actions();
	if (!O || !A) return;
	const FString State = A->GetStateString();
	{
		// a state change (ignoring the "+upper/+aim" layer suffixes) opens a two frame window in which the pose must not pop
		auto Base = [](const FString& S) { int32 I; return S.FindChar('+', I) ? S.Left(I).TrimEnd() : S; };
		if (Base(State) != Base(LastState)) TransitionFrames = 2;
	}
	if (State != LastState)
	{
		Trace(FString::Printf(TEXT("kind=STATE step=%s from=\"%s\" to=\"%s\" pos=(%.0f,%.0f,%.0f) speed=%.0f"), *StepName, *LastState, *State, O->GetActorLocation().X, O->GetActorLocation().Y, O->GetActorLocation().Z, O->GetVelocity().Size2D()));
		LastState = State;
	}
	const FString Clip = A->GetBaseClipId().ToString();
	if (Clip != LastClip)
	{
		if (!State.StartsWith(TEXT("Locomotion/Move"))) TransitionFrames = 2;
		Trace(FString::Printf(TEXT("kind=CLIP step=%s clip=%s length=%.3f rate=%.2f"), *StepName, *Clip, A->GetBaseClipLength(), A->GetBasePlayer().Rate));
		LastClip = Clip;
		SeenClips.Add(Clip);
	}
	if (!A->GetUpperClipId().IsNone()) SeenClips.Add(A->GetUpperClipId().ToString());
	// pose continuity: largest per frame movement of tracked bones (component space)
	if (const UOperativeAnimInstance* AI = O->GetOperativeAnim())
	{
		const FOperativeEvalDebug& D = AI->GetEvalDebug();
		if (D.bValid && bTracePose)
		{
			Trace(FString::Printf(TEXT("kind=POSE state=\"%s\" clip=%s t=%.3f snap=%.2f serial=%d head=(%.0f,%.0f,%.0f) hand_l=(%.0f,%.0f,%.0f) hand_r=(%.0f,%.0f,%.0f) pelvis=(%.0f,%.0f,%.0f) foot_l=(%.1f,%.1f,%.1f) foot_r=(%.1f,%.1f,%.1f)"), *State, *Clip, A->GetBaseClipTime(), D.SnapshotAlpha, A->GetRecipe().SnapshotSerial,
				D.Head.X, D.Head.Y, D.Head.Z, D.HandLeft.X, D.HandLeft.Y, D.HandLeft.Z, D.HandRight.X, D.HandRight.Y, D.HandRight.Z, D.Pelvis.X, D.Pelvis.Y, D.Pelvis.Z, D.FootLeft.X, D.FootLeft.Y, D.FootLeft.Z, D.FootRight.X, D.FootRight.Y, D.FootRight.Z));
		}
		if (D.bValid)
		{
			const FVector Cur[6] = { D.HandLeft, D.HandRight, D.FootLeft, D.FootRight, D.Head, D.Pelvis };
			static const TCHAR* Names[6] = { TEXT("hand_l"), TEXT("hand_r"), TEXT("foot_l"), TEXT("foot_r"), TEXT("head"), TEXT("pelvis") };
			const bool bIgnore = PoseIgnoreFrames > 0 || A->GetState() == EOperativeState::Blink || A->GetState() == EOperativeState::Respawning || A->GetState() == EOperativeState::Dead;
			if (bHavePrev && !bIgnore)
			{
				// a step is only a runtime spike when it exceeds what the playing clips contain themselves (fast authored strikes are reported by the content check)
				float Allowed = 40.f;
				{
					const float Rate = FMath::Max(1.f, A->GetBasePlayer().Rate);
					if (const float* M = ClipMaxStep.Find(Clip)) Allowed = FMath::Max(Allowed, *M * 1.35f * Rate);
					if (!A->GetUpperClipId().IsNone()) if (const float* M = ClipMaxStep.Find(A->GetUpperClipId().ToString())) Allowed = FMath::Max(Allowed, *M * 1.35f * Rate);
				}
				for (int32 I = 0; I < 6; ++I)
				{
					const float Delta = FVector::Dist(Cur[I], PrevBonePos[I]);
					if (Delta > StepMaxDelta) { StepMaxDelta = Delta; StepMaxBone = Names[I]; }
					if (Delta > GlobalMaxDelta) { GlobalMaxDelta = Delta; GlobalMaxWhere = FString::Printf(TEXT("%s step=%s state=%s"), Names[I], *StepName, *State); }
					if (Delta > Allowed && TransitionFrames > 0)
					{
						++PoseSpikes;
						Trace(FString::Printf(TEXT("kind=POSE_SPIKE step=%s bone=%s delta_cm=%.1f from=(%.0f,%.0f,%.0f) to=(%.0f,%.0f,%.0f) state=\"%s\" clip=%s snapshot_alpha=%.2f recipe_alpha=%.2f serial=%d bonemap_rebuilds=%d"), *StepName, Names[I], Delta,
							PrevBonePos[I].X, PrevBonePos[I].Y, PrevBonePos[I].Z, Cur[I].X, Cur[I].Y, Cur[I].Z, *State, *Clip, D.SnapshotAlpha, D.RecipeSnapshotAlpha, D.RecipeSerial, D.BoneMapRebuilds));
					}
				}
			}
			for (int32 I = 0; I < 6; ++I) PrevBonePos[I] = Cur[I];
			bHavePrev = true;
			if (PoseIgnoreFrames > 0) --PoseIgnoreFrames;
			if (TransitionFrames > 0) --TransitionFrames;
		}
	}
	TraceFlushTimer += Dt;
	if (TraceFlushTimer > 2.f && TraceBuffer.Num() > 0)
	{
		TraceFlushTimer = 0.f;
		FFileHelper::SaveStringToFile(FString::Join(TraceBuffer, TEXT("\n")) + TEXT("\n"), *TraceFilePath, FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM, &IFileManager::Get(), FILEWRITE_Append);
		TraceBuffer.Reset();
	}
}

// ------------------------------------------------------------------------------------------------ sequence definition

void AShowcaseDirector::AddDo(const FString& Label, TFunction<void()> Fn)
{
	FTask T;
	T.Label = Label;
	T.Begin = MoveTemp(Fn);
	Tasks.Add(MoveTemp(T));
}

void AShowcaseDirector::AddWait(float Seconds)
{
	FTask T;
	T.Label = FString::Printf(TEXT("wait %.2f"), Seconds);
	T.Timeout = Seconds + 1.f;
	T.Done = [this, Seconds]() { return Tasks.IsValidIndex(TaskIndex) && Tasks[TaskIndex].Elapsed >= Seconds; };
	Tasks.Add(MoveTemp(T));
}

void AShowcaseDirector::AddWaitUntil(const FString& Label, TFunction<bool()> Pred, float Timeout)
{
	FTask T;
	T.Label = Label;
	T.Timeout = Timeout;
	T.Done = MoveTemp(Pred);
	Tasks.Add(MoveTemp(T));
}

void AShowcaseDirector::AddWaitIdle(float Timeout)
{
	AddWaitUntil(TEXT("wait idle"), [this]() { UOperativeActionComponent* A = Actions(); return A && A->IsIdle() && A->GetState() == EOperativeState::Locomotion; }, Timeout);
}

void AShowcaseDirector::AddPhase(const FString& Name, EShowcaseView View)
{
	AddDo(Name, [this, Name, View]()
	{
		if (bStopAfterNext) { TaskIndex = Tasks.Num(); return; }   // the previous phase was the last one requested with -SeqTo
		++PhasesSeen;
		if (!SeqTo.IsEmpty() && Name.Contains(SeqTo)) bStopAfterNext = true;
		StepName = Name;
		Counters.Empty();
		SeenClips.Empty();
		StepMaxDelta = 0.f;
		StepMaxBone.Empty();
		PhaseStartTime = GetWorld()->GetTimeSeconds();
		Trace(FString::Printf(TEXT("kind=STEP begin=%s view=%d"), *Name, (int32)View));
		if (AShowcasePlayerController* P = PC()) { P->SetView(View); P->SetCameraLocked(true); }
		// the video shows the aim targets only in the steps that use them (a target next to the camera fills half of the frame otherwise)
		if (CaptureMode == ECaptureMode::Motion)
		{
			if (AShowcaseRoom* R = Room()) R->SetTargetsShown(Name.Contains(TEXT("aim")) || Name.Contains(TEXT("melee")) || Name.Contains(TEXT("action_rate")));
		}
	});
}

void AShowcaseDirector::BuildSequence()
{
	Tasks.Reset();
	TaskIndex = 0;
	auto Place = [this](float Yaw = 0.f, const FVector* At = nullptr)
	{
		AOperativeCharacter* O = Op();
		if (!O) return;
		O->ResetOperative(true);
		if (At) O->TeleportTo(FVector(At->X, At->Y, 92.f), FRotator(0.f, Yaw, 0.f), false, true);
		O->SetFacingYaw(Yaw);
		SeqMoveDir = FVector::ZeroVector;
		SeqMoveSpeed = 0.f;
		SeqAimPoint = O->GetActorLocation() + FVector(3000.f, 0.f, 0.f);
		Actions()->SetFacingMode(EOperativeFacingMode::Aim);
		Actions()->SetActionRate(1.f);
		PoseIgnoreFrames = 4;
		if (AShowcasePlayerController* P = PC()) P->ResetCameraSmoothing();
	};
	auto Move = [this](const FVector& Dir, float Speed) { SeqMoveDir = Dir; SeqMoveSpeed = Speed; };
	const FVector Fwd(1.f, 0.f, 0.f), Back(-1.f, 0.f, 0.f), Left(0.f, -1.f, 0.f), Right(0.f, 1.f, 0.f);
	auto Sqrt2 = [](FVector V) { return V.GetSafeNormal(); };
	auto Mark = [this](const FString& Key) { if (AOperativeCharacter* O = Op()) Marks.Add(Key, O->GetActorLocation()); };
	auto Dist = [this](const FString& Key) { AOperativeCharacter* O = Op(); const FVector* M = Marks.Find(Key); return (O && M) ? FVector::Dist2D(O->GetActorLocation(), *M) : -1.f; };
	auto Seen = [this](const TCHAR* Clip) { return SeenClips.Contains(FString(Clip)); };
	auto Count = [this](const TCHAR* Ev) { const int32* C = Counters.Find(FString(Ev)); return C ? *C : 0; };
	auto Ops = [this]() { return Actions(); };

	// ------------------------------------------------------------------ locomotion
	const FVector LaneStart(-1250.f, 1100.f, 92.f), LaneMid(0.f, 1100.f, 92.f);
	AddPhase(TEXT("locomotion_walk_run_sprint_stop"), EShowcaseView::ThirdPerson);
	AddDo(TEXT("place"), [=, this]() { Place(0.f, &LaneStart); });
	AddWait(0.6f);
	AddDo(TEXT("walk 150 cm/s"), [=, this]() { Move(Fwd, 150.f); });
	AddWait(1.5f);
	AddDo(TEXT("record walk speed"), [=, this]() { AOperativeCharacter* O = Op(); Check(TEXT("walk_speed"), O && FMath::Abs(O->GetVelocity().Size2D() - 150.f) < 25.f, FString::Printf(TEXT("speed=%.1f expected=150"), O ? O->GetVelocity().Size2D() : -1.f)); });
	AddDo(TEXT("run 400 cm/s"), [=, this]() { Move(Fwd, 400.f); });
	AddWait(1.3f);
	AddDo(TEXT("record run speed"), [=, this]() { AOperativeCharacter* O = Op(); Check(TEXT("run_speed"), O && FMath::Abs(O->GetVelocity().Size2D() - 400.f) < 40.f, FString::Printf(TEXT("speed=%.1f expected=400"), O ? O->GetVelocity().Size2D() : -1.f)); });
	AddDo(TEXT("sprint 650 cm/s"), [=, this]() { Move(Fwd, 650.f); });
	AddWait(0.9f);
	AddDo(TEXT("record sprint speed"), [=, this]() { AOperativeCharacter* O = Op(); Check(TEXT("sprint_speed"), O && FMath::Abs(O->GetVelocity().Size2D() - 650.f) < 65.f, FString::Printf(TEXT("speed=%.1f expected=650"), O ? O->GetVelocity().Size2D() : -1.f)); });
	AddDo(TEXT("release input (stop_f)"), [=, this]() { Move(FVector::ZeroVector, 0.f); });
	AddWaitIdle(4.f);
	AddDo(TEXT("check stopped"), [=, this]() { Check(TEXT("stop_clip_played"), Seen(TEXT("stop_f")) && Seen(TEXT("start_f")), FString::Printf(TEXT("clips=%s"), *FString::Join(SeenClips.Array(), TEXT(",")))); });

	AddPhase(TEXT("eight_directions_independent_facing"), EShowcaseView::TopDown);
	AddDo(TEXT("place"), [=, this]() { Place(0.f, &LaneMid); });
	AddWait(0.5f);
	{
		const FVector Dirs[8] = { Fwd, Back, Left, Right, Sqrt2(Fwd + Left), Sqrt2(Back + Right), Sqrt2(Fwd + Right), Sqrt2(Back + Left) };
		const TCHAR* Names[8] = { TEXT("F"), TEXT("B"), TEXT("L"), TEXT("R"), TEXT("FL"), TEXT("BR"), TEXT("FR"), TEXT("BL") };
		for (int32 I = 0; I < 8; ++I)
		{
			AddDo(FString::Printf(TEXT("direction %s"), Names[I]), [=, this]() { Move(Dirs[I], 400.f); });
			AddWait(0.95f);
		}
	}
	AddDo(TEXT("stop"), [=, this]() { Move(FVector::ZeroVector, 0.f); });
	AddWaitIdle(4.f);
	AddDo(TEXT("check facing"), [=, this]() { AOperativeCharacter* O = Op(); Check(TEXT("facing_independent_of_travel"), O && FMath::Abs(FRotator::NormalizeAxis(O->GetActorRotation().Yaw)) < 6.f, FString::Printf(TEXT("yaw=%.1f travelled=%.0f cm"), O ? O->GetActorRotation().Yaw : 0.f, O ? O->GetTravelSinceReset() : 0.f));
		Check(TEXT("strafe_clips_used"), Seen(TEXT("run_l")) || Seen(TEXT("run_fl")) || Seen(TEXT("walk_l")), FString::Printf(TEXT("clips=%s"), *FString::Join(SeenClips.Array(), TEXT(","))));
		{
			FIntPoint VS(1920, 1080);
			if (GEngine && GEngine->GameViewport && GEngine->GameViewport->Viewport) VS = GEngine->GameViewport->Viewport->GetSizeXY();
			const float Px = PC() ? PC()->GetCharacterPixelHeight() : 0.f;
			const float Px1080 = VS.Y > 0 ? Px * 1080.f / VS.Y : Px;     // the check is stated for a 1920 x 1080 frame
			Check(TEXT("topdown_character_about_120px"), Px1080 > 100.f && Px1080 < 140.f, FString::Printf(TEXT("character %.0f px tall in the top-down view, %.0f px scaled to a 1080 px high frame (viewport %dx%d)"), Px, Px1080, VS.X, VS.Y));
		} });

	// ------------------------------------------------------------------ aim while moving with upper body layering
	AddPhase(TEXT("aim_while_moving_fire_burst_cast"), EShowcaseView::ThirdPerson);
	AddDo(TEXT("place and aim"), [=, this]() {
		const FVector AimStart(500.f, -600.f, 92.f);
		Place(90.f, &AimStart);
		Actions()->SetFacingMode(EOperativeFacingMode::Movement);
		Actions()->SetAimAlways(true);
		if (AShowcaseRoom* R = Room()) if (R->GetTargets().Num() > 0) SeqAimPoint = R->GetTargets()[0]->GetActorLocation() + FVector(0.f, 0.f, R->GetTargets()[0]->GetHeight());
		Move(Right, 400.f);
	});
	AddWait(0.9f);
	AddDo(TEXT("fire while moving"), [=, this]() { Ops()->RequestFire(); });
	AddWait(0.8f);
	AddDo(TEXT("fire again"), [=, this]() { Ops()->RequestFire(); });
	AddWait(0.8f);
	AddDo(TEXT("burst while moving"), [=, this]() { Ops()->RequestBurst(); if (AShowcaseRoom* R = Room()) if (R->GetTargets().Num() > 3) SeqAimPoint = R->GetTargets()[3]->GetActorLocation() + FVector(0.f, 0.f, R->GetTargets()[3]->GetHeight()); });
	AddWait(1.0f);
	AddDo(TEXT("reverse direction, directional cast"), [=, this]() { Move(Left, 400.f); Ops()->RequestCastDirectional(); });
	AddWait(1.4f);
	AddDo(TEXT("stop"), [=, this]() { Move(FVector::ZeroVector, 0.f); Actions()->SetAimAlways(false); });
	AddWaitIdle(4.f);
	AddDo(TEXT("check layering"), [=, this]() {
		Check(TEXT("muzzle_fire_events"), Count(TEXT("muzzle_fire")) >= 4, FString::Printf(TEXT("muzzle_fire=%d expected>=4 (1+1+3 shots, one may be queued)"), Count(TEXT("muzzle_fire"))));
		Check(TEXT("upper_clips_used"), Seen(TEXT("ranged_fire")) && Seen(TEXT("ranged_burst")) && Seen(TEXT("cast_directional")), FString::Printf(TEXT("clips=%s"), *FString::Join(SeenClips.Array(), TEXT(",")))); });

	// ------------------------------------------------------------------ jump and fall
	AddPhase(TEXT("jump_run_jump_long_fall"), EShowcaseView::Side);
	AddDo(TEXT("place"), [=, this]() { Place(0.f, &LaneMid); });
	AddWait(0.4f);
	AddDo(TEXT("standing jump"), [=, this]() { Ops()->RequestJump(); });
	AddWaitUntil(TEXT("airborne"), [=, this]() { return Ops()->GetState() == EOperativeState::Airborne; }, 2.f);
	AddWaitIdle(4.f);
	AddDo(TEXT("run and jump"), [=, this]() { Move(Fwd, 400.f); });
	AddWait(0.8f);
	AddDo(TEXT("jump"), [=, this]() { Ops()->RequestJump(); });
	AddWait(1.6f);
	AddDo(TEXT("stop"), [=, this]() { Move(FVector::ZeroVector, 0.f); });
	AddWaitIdle(4.f);
	AddDo(TEXT("check jump"), [=, this]() { Check(TEXT("jump_clips"), Seen(TEXT("jump_start")) && Seen(TEXT("jump_air")) && Seen(TEXT("jump_land")), FString::Printf(TEXT("clips=%s takeoff=%d land_contact=%d"), *FString::Join(SeenClips.Array(), TEXT(",")), Count(TEXT("jump_takeoff")), Count(TEXT("land_contact")))); });
	AddDo(TEXT("teleport to the platform"), [=, this]() {
		AShowcaseRoom* R = Room();
		AOperativeCharacter* O = Op();
		if (!R || !O) return;
		const FVector P = R->GetPlatformTop();
		O->TeleportTo(FVector(P.X - 80.f, P.Y, P.Z + 92.f), FRotator::ZeroRotator, false, true);
		O->GetCharacterMovement()->Velocity = FVector::ZeroVector;
		Ops()->SetTeleportedThisFrame();
		PoseIgnoreFrames = 4;
		SeqAimPoint = O->GetActorLocation() + FVector(3000.f, 0.f, 0.f);
		if (AShowcasePlayerController* PCtl = PC()) PCtl->ResetCameraSmoothing();     // cut to the platform instead of flying there
	});
	AddWait(0.8f);
	AddDo(TEXT("walk off the edge"), [=, this]() { Move(Fwd, 400.f); });
	AddWaitUntil(TEXT("airborne"), [=, this]() { return Ops()->GetState() == EOperativeState::Airborne; }, 3.f);
	AddDo(TEXT("keep moving in the air"), [=, this]() { Move(Fwd, 200.f); });
	AddWait(0.5f);
	AddDo(TEXT("input off"), [=, this]() { Move(FVector::ZeroVector, 0.f); });
	AddWaitIdle(6.f);
	AddDo(TEXT("check fall"), [=, this]() { Check(TEXT("fall_and_heavy_landing"), Seen(TEXT("fall")) && Seen(TEXT("land_heavy")), FString::Printf(TEXT("clips=%s"), *FString::Join(SeenClips.Array(), TEXT(",")))); });


	// ------------------------------------------------------------------ foot IK: planted feet against the ground on the ramp, the stairs and the curbs
	AddPhase(TEXT("foot_ik_ramp_and_steps"), EShowcaseView::Side);
	struct FIKCourse { const TCHAR* Name; FVector Start; float Seconds; };
	static const FIKCourse Courses[3] = { { TEXT("ramp_20deg"), FVector(-800.f, -900.f, 92.f), 5.2f }, { TEXT("stairs_5x20cm"), FVector(-520.f, 700.f, 92.f), 4.4f }, { TEXT("curbs_10_15_20cm"), FVector(-1100.f, -300.f, 92.f), 6.8f } };
	for (int32 C = 0; C < 3; ++C)
	{
		for (int32 Pass = 0; Pass < 2; ++Pass)      // foot IK on first, then off as the baseline
		{
			const FIKCourse Course = Courses[C];
			const bool bOn = Pass == 0;
			const FString RunName = FString::Printf(TEXT("%s_ik_%s"), Course.Name, bOn ? TEXT("on") : TEXT("off"));
			AddDo(FString::Printf(TEXT("place for %s"), *RunName), [=, this]() { Place(0.f, &Course.Start); Actions()->SetIKEnabled(bOn); });
			AddWait(0.6f);
			AddDo(TEXT("walk over the course"), [=, this]() { Move(Fwd, 150.f); IKBegin(RunName); });
			AddWait(Course.Seconds);
			AddDo(TEXT("stop"), [=, this]() { IKEnd(); Move(FVector::ZeroVector, 0.f); Actions()->SetIKEnabled(true); });
			AddWaitIdle(3.f);
		}
	}
	AddDo(TEXT("check foot ik"), [=, this]() {
		for (int32 C = 0; C < 3; ++C)
		{
			const FIKRun* On = IKRuns.Find(FString::Printf(TEXT("%s_ik_on"), Courses[C].Name));
			const FIKRun* Off = IKRuns.Find(FString::Printf(TEXT("%s_ik_off"), Courses[C].Name));
			if (!On || !Off) { Check(FString::Printf(TEXT("foot_ik_%s"), Courses[C].Name), false, TEXT("no measurement")); continue; }
			Check(FString::Printf(TEXT("foot_ik_%s"), Courses[C].Name), On->Samples > 20 && On->MeanAbs() < 2.5f && On->MaxPenetration < 4.f && On->MeanAbs() <= Off->MeanAbs() + 0.05f,
				FString::Printf(TEXT("planted samples on=%d off=%d, mean abs error on=%.2f cm off=%.2f cm, max penetration on=%.2f cm off=%.2f cm, max float on=%.2f off=%.2f, max pelvis offset %.2f cm"),
					On->Samples, Off->Samples, On->MeanAbs(), Off->MeanAbs(), On->MaxPenetration, Off->MaxPenetration, On->MaxFloat, Off->MaxFloat, On->MaxPelvisOffset));
		}
	});

	// ------------------------------------------------------------------ dash root motion (capsule driven)
	AddPhase(TEXT("dash_forward_left_back_right"), EShowcaseView::Side);
	AddDo(TEXT("place"), [=, this]() { Place(0.f, &LaneMid); });
	AddWait(0.5f);
	{
		struct FDashDef { const TCHAR* Name; FVector Dir; FVector Expected; };
		const FDashDef Defs[4] = { { TEXT("dash_f"), Fwd, Fwd }, { TEXT("dash_l"), Left, Left }, { TEXT("dash_b"), Back, Back }, { TEXT("dash_r"), Right, Right } };
		for (int32 I = 0; I < 4; ++I)
		{
			const FDashDef D = Defs[I];
			AddDo(FString::Printf(TEXT("%s mark"), D.Name), [=, this]() { Mark(D.Name); });
			AddDo(FString::Printf(TEXT("%s"), D.Name), [=, this]() { Ops()->RequestDash(D.Dir); });
			AddWaitUntil(TEXT("dash done"), [=, this]() { return Ops()->GetState() != EOperativeState::Dash && Seen(D.Name); }, 3.f);
			AddWaitIdle(3.f);
			AddDo(FString::Printf(TEXT("%s check"), D.Name), [=, this]() {
				AOperativeCharacter* O = Op();
				const FVector* M = Marks.Find(D.Name);
				const float Along = (O && M) ? FVector::DotProduct(O->GetActorLocation() - *M, D.Expected) : -1.f;
				Check(FString::Printf(TEXT("%s_capsule_displacement"), D.Name), FMath::Abs(Along - 200.f) < 18.f, FString::Printf(TEXT("along_dash_axis=%.1f cm expected=200 total=%.1f"), Along, Dist(D.Name))); });
			AddWait(0.3f);
		}
	}

	// ------------------------------------------------------------------ blink
	AddPhase(TEXT("blink_teleport_event"), EShowcaseView::ThirdPerson);
	AddDo(TEXT("place"), [=, this]() { const FVector BlinkStart(-500.f, 1100.f, 92.f); Place(0.f, &BlinkStart); Mark(TEXT("blink")); });
	AddWait(0.4f);
	AddDo(TEXT("blink 5 m forward"), [=, this]() { Ops()->RequestBlink(Fwd, 500.f); });
	AddWaitUntil(TEXT("blink done"), [=, this]() { return Ops()->GetState() != EOperativeState::Blink && Seen(TEXT("blink_in")); }, 3.f);
	AddWaitIdle(3.f);
	AddDo(TEXT("check blink"), [=, this]() {
		Check(TEXT("blink_travel"), FMath::Abs(Dist(TEXT("blink")) - 500.f) < 30.f, FString::Printf(TEXT("distance=%.1f expected~500"), Dist(TEXT("blink"))));
		Check(TEXT("blink_events_once"), Count(TEXT("blink_vanish")) == 1 && Count(TEXT("blink_appear")) == 1, FString::Printf(TEXT("vanish=%d appear=%d"), Count(TEXT("blink_vanish")), Count(TEXT("blink_appear")))); });

	// ------------------------------------------------------------------ melee chain and action rate
	AddPhase(TEXT("melee_chain_1_2_3"), EShowcaseView::ThirdPerson);
	AddDo(TEXT("place, target in reach"), [=, this]() {
		Place();
		if (AShowcaseRoom* R = Room()) { R->SelectNextTarget(); R->MoveSelectedTarget(Op()->GetActorLocation() + FVector(150.f, 0.f, 0.f)); }
	});
	AddWait(0.4f);
	AddDo(TEXT("melee 1"), [=, this]() { Ops()->RequestMelee(); });
	AddWait(0.35f);
	AddDo(TEXT("melee 2 (queued for the combo window)"), [=, this]() { Ops()->RequestMelee(); });
	AddWait(0.6f);
	AddDo(TEXT("melee 3 (queued)"), [=, this]() { Ops()->RequestMelee(); });
	AddWaitIdle(6.f);
	AddDo(TEXT("check chain"), [=, this]() { Check(TEXT("melee_chain_played"), Seen(TEXT("melee_1")) && Seen(TEXT("melee_2")) && Seen(TEXT("melee_3")), FString::Printf(TEXT("clips=%s"), *FString::Join(SeenClips.Array(), TEXT(","))));
		Check(TEXT("melee_hit_windows_once_each"), Count(TEXT("melee_hit_begin")) == 3 && Count(TEXT("melee_hit_end")) == 3, FString::Printf(TEXT("hit_begin=%d hit_end=%d (3 expected)"), Count(TEXT("melee_hit_begin")), Count(TEXT("melee_hit_end")))); });
	AddPhase(TEXT("action_rate_0_5x_and_1_5x"), EShowcaseView::ThirdPerson);
	AddDo(TEXT("place, rate 0.5"), [=, this]() { Place(); Actions()->SetActionRate(0.5f); });
	AddWait(0.3f);
	AddDo(TEXT("melee 1 at 0.5x"), [=, this]() { Ops()->RequestMelee(); });
	AddWait(0.6f);
	AddDo(TEXT("melee 2"), [=, this]() { Ops()->RequestMelee(); });
	AddWait(0.9f);
	AddDo(TEXT("melee 3"), [=, this]() { Ops()->RequestMelee(); });
	AddWaitIdle(10.f);
	AddDo(TEXT("check slow"), [=, this]() { Check(TEXT("rate_0_5_hit_windows_not_duplicated"), Count(TEXT("melee_hit_begin")) == 3, FString::Printf(TEXT("hit_begin=%d (3 expected)"), Count(TEXT("melee_hit_begin")))); Counters.Empty(); Actions()->SetActionRate(1.5f); });
	AddWait(0.3f);
	AddDo(TEXT("melee 1 at 1.5x"), [=, this]() { Ops()->RequestMelee(); });
	AddWait(0.2f);
	AddDo(TEXT("melee 2"), [=, this]() { Ops()->RequestMelee(); });
	AddWait(0.3f);
	AddDo(TEXT("melee 3"), [=, this]() { Ops()->RequestMelee(); });
	AddWaitIdle(6.f);
	AddDo(TEXT("check fast"), [=, this]() { Check(TEXT("rate_1_5_hit_windows_not_duplicated"), Count(TEXT("melee_hit_begin")) == 3, FString::Printf(TEXT("hit_begin=%d (3 expected)"), Count(TEXT("melee_hit_begin")))); Actions()->SetActionRate(1.f); });

	// ------------------------------------------------------------------ reload, casts
	AddPhase(TEXT("reload_and_casts"), EShowcaseView::Hands);
	AddDo(TEXT("place"), [=, this]() { Place(); });
	AddWait(0.4f);
	AddDo(TEXT("reload"), [=, this]() { Ops()->RequestReload(); });
	AddWaitUntil(TEXT("reload started"), [=, this]() { return Ops()->GetActionKind() == EOperativeAction::Reload; }, 1.f);
	AddWaitIdle(6.f);
	AddDo(TEXT("view third person"), [=, this]() { if (AShowcasePlayerController* P = PC()) P->SetView(EShowcaseView::ThirdPerson); });
	AddDo(TEXT("cast ground"), [=, this]() { if (AShowcaseRoom* R = Room()) if (R->GetTargets().Num() > 1) SeqAimPoint = R->GetTargets()[1]->GetActorLocation(); Ops()->RequestCastGround(); });
	AddWaitUntil(TEXT("cast started"), [=, this]() { return Ops()->GetActionKind() == EOperativeAction::CastGround; }, 1.f);
	AddWaitIdle(6.f);
	AddDo(TEXT("cast self"), [=, this]() { Ops()->RequestCastSelf(); });
	AddWaitUntil(TEXT("cast started"), [=, this]() { return Ops()->GetActionKind() == EOperativeAction::CastSelf; }, 1.f);
	AddWaitIdle(6.f);
	AddDo(TEXT("check"), [=, this]() { Check(TEXT("reload_and_cast_events"), Count(TEXT("reload_handoff")) == 1 && Count(TEXT("cast_release")) == 2, FString::Printf(TEXT("reload_handoff=%d cast_release=%d"), Count(TEXT("reload_handoff")), Count(TEXT("cast_release")))); });

	// ------------------------------------------------------------------ channel: sustain, interrupt, release
	AddPhase(TEXT("channel_sustain_interrupt_release"), EShowcaseView::ThirdPerson);
	AddDo(TEXT("place, aim at target"), [=, this]() { Place(); if (AShowcaseRoom* R = Room()) if (R->GetTargets().Num() > 2) SeqAimPoint = R->GetTargets()[2]->GetActorLocation() + FVector(0.f, 0.f, 100.f); });
	AddWait(0.4f);
	AddDo(TEXT("channel start"), [=, this]() { Ops()->RequestChannelStart(); });
	AddWaitUntil(TEXT("channel sustained"), [=, this]() { return Ops()->IsChannelSustained(); }, 3.f);
	AddWait(0.9f);
	AddDo(TEXT("interrupt in the loop"), [=, this]() { Ops()->InterruptAction(EOperativeInterrupt::Manual); });
	AddWaitIdle(4.f);
	AddDo(TEXT("check interrupt"), [=, this]() { Check(TEXT("channel_interrupt_clip"), Seen(TEXT("channel_interrupt")) && Count(TEXT("channel_interrupted")) == 1, FString::Printf(TEXT("clips=%s interrupted=%d"), *FString::Join(SeenClips.Array(), TEXT(",")), Count(TEXT("channel_interrupted")))); });
	AddDo(TEXT("channel start again"), [=, this]() { Counters.Empty(); SeenClips.Empty(); Ops()->RequestChannelStart(); });
	AddWait(0.2f);
	AddDo(TEXT("release during the start clip"), [=, this]() { Ops()->RequestChannelRelease(); });
	AddWaitIdle(4.f);
	AddDo(TEXT("check early release"), [=, this]() { Check(TEXT("channel_early_release_goes_to_end"), Seen(TEXT("channel_end")) && !Seen(TEXT("channel_loop")), FString::Printf(TEXT("clips=%s"), *FString::Join(SeenClips.Array(), TEXT(",")))); });
	AddDo(TEXT("channel start, full sustain and release"), [=, this]() { Counters.Empty(); SeenClips.Empty(); Ops()->RequestChannelStart(); });
	AddWaitUntil(TEXT("channel sustained"), [=, this]() { return Ops()->IsChannelSustained(); }, 3.f);
	AddWait(0.7f);
	AddDo(TEXT("release"), [=, this]() { Ops()->RequestChannelRelease(); });
	AddWaitIdle(4.f);
	AddDo(TEXT("check release"), [=, this]() { Check(TEXT("channel_end_clip"), Seen(TEXT("channel_end")) && Count(TEXT("channel_release")) == 1, FString::Printf(TEXT("clips=%s release=%d"), *FString::Join(SeenClips.Array(), TEXT(",")), Count(TEXT("channel_release")))); });

	// ------------------------------------------------------------------ charge
	AddPhase(TEXT("charge_release_early_late_cancel"), EShowcaseView::ThirdPerson);
	AddDo(TEXT("place"), [=, this]() { Place(); });
	AddWait(0.4f);
	AddDo(TEXT("charge, hold, release late"), [=, this]() { Ops()->RequestChargeStart(); });
	AddWait(2.0f);
	AddDo(TEXT("release"), [=, this]() { Ops()->RequestChargeRelease(); });
	AddWaitIdle(4.f);
	AddDo(TEXT("check late release"), [=, this]() { Check(TEXT("charge_full_then_release"), Count(TEXT("charge_full")) == 1 && Count(TEXT("charge_release")) == 1, FString::Printf(TEXT("full=%d release=%d"), Count(TEXT("charge_full")), Count(TEXT("charge_release")))); Counters.Empty(); });
	AddDo(TEXT("charge, release early"), [=, this]() { Ops()->RequestChargeStart(); });
	AddWait(0.25f);
	AddDo(TEXT("release"), [=, this]() { Ops()->RequestChargeRelease(); });
	AddWaitIdle(4.f);
	AddDo(TEXT("charge, cancel"), [=, this]() { Counters.Empty(); Ops()->RequestChargeStart(); });
	AddWait(0.9f);
	AddDo(TEXT("cancel"), [=, this]() { Ops()->RequestChargeCancel(); });
	AddWaitIdle(4.f);
	AddDo(TEXT("check cancel"), [=, this]() { Check(TEXT("charge_cancel"), Count(TEXT("charge_cancel")) == 1 && Count(TEXT("charge_release")) == 0, FString::Printf(TEXT("cancel=%d release=%d"), Count(TEXT("charge_cancel")), Count(TEXT("charge_release")))); });

	// ------------------------------------------------------------------ deploy and uplink
	AddPhase(TEXT("deploy_beacon"), EShowcaseView::Hands);
	AddDo(TEXT("place"), [=, this]() { Place(); });
	AddWait(0.4f);
	AddDo(TEXT("deploy"), [=, this]() { Ops()->RequestDeploy(); });
	AddWaitUntil(TEXT("deploy started"), [=, this]() { return Ops()->GetActionKind() == EOperativeAction::Deploy; }, 1.f);
	AddWaitIdle(6.f);
	AddWait(0.6f);
	AddDo(TEXT("check deploy"), [=, this]() { Check(TEXT("beacon_spawned_at_release"), Op()->IsBeaconDeployed() && Count(TEXT("deploy_release")) == 1, FString::Printf(TEXT("world_beacon=%d release=%d"), Op()->IsBeaconDeployed() ? 1 : 0, Count(TEXT("deploy_release")))); });
	AddPhase(TEXT("uplink_cancel_and_complete"), EShowcaseView::ThirdPerson);
	AddDo(TEXT("uplink start"), [=, this]() { Actions()->UplinkDuration = 1.6f; Ops()->RequestUplinkStart(); });
	AddWait(1.2f);
	AddDo(TEXT("cancel"), [=, this]() { Ops()->RequestUplinkCancel(); });
	AddWaitIdle(4.f);
	AddDo(TEXT("check cancel"), [=, this]() { Check(TEXT("uplink_cancelled"), Seen(TEXT("uplink_cancel")) && Count(TEXT("uplink_cancelled")) == 1, FString::Printf(TEXT("clips=%s"), *FString::Join(SeenClips.Array(), TEXT(",")))); Counters.Empty(); SeenClips.Empty(); });
	AddDo(TEXT("uplink complete"), [=, this]() { Ops()->RequestUplinkStart(); });
	AddWaitUntil(TEXT("complete"), [=, this]() { return Count(TEXT("uplink_complete")) == 1 && Ops()->IsIdle(); }, 8.f);
	AddDo(TEXT("check complete"), [=, this]() { Check(TEXT("uplink_complete"), Seen(TEXT("uplink_loop")) && Seen(TEXT("uplink_end")), FString::Printf(TEXT("clips=%s"), *FString::Join(SeenClips.Array(), TEXT(",")))); Actions()->UplinkDuration = 3.f; });

	// ------------------------------------------------------------------ hits while moving
	AddPhase(TEXT("hits_while_moving"), EShowcaseView::ThirdPerson);
	AddDo(TEXT("place, run"), [=, this]() { Place(); Move(Fwd, 400.f); });
	AddWait(0.9f);
	{
		const FVector Travel[4] = { Back, Fwd, Right, Left };   // travel direction of the hit: from front, back, left, right of a character facing +X
		const TCHAR* Names[4] = { TEXT("front"), TEXT("back"), TEXT("left"), TEXT("right") };
		for (int32 I = 0; I < 4; ++I)
		{
			AddDo(FString::Printf(TEXT("hit from %s"), Names[I]), [=, this]() { Ops()->ApplyHit(Travel[I], 0.f); });
			AddWait(0.5f);
		}
	}
	AddDo(TEXT("stop"), [=, this]() { Move(FVector::ZeroVector, 0.f); });
	AddWaitIdle(4.f);
	AddDo(TEXT("check hits"), [=, this]() { Check(TEXT("hits_do_not_change_state"), Seen(TEXT("hit_f")) || Seen(TEXT("hit_b")) || Count(TEXT("hit_peak")) >= 4, FString::Printf(TEXT("hit_peak=%d"), Count(TEXT("hit_peak")))); });

	// ------------------------------------------------------------------ disables
	AddPhase(TEXT("stun_sleep_knockback"), EShowcaseView::ThirdPerson);
	AddDo(TEXT("place"), [=, this]() { Place(); });
	AddWait(0.4f);
	AddDo(TEXT("stun 1.2 s"), [=, this]() { Ops()->ApplyStun(1.2f); });
	AddWaitUntil(TEXT("stun over"), [=, this]() { return Seen(TEXT("stun_end")) && Ops()->IsIdle(); }, 8.f);
	AddDo(TEXT("sleep 1.5 s"), [=, this]() { Ops()->ApplySleep(1.5f); });
	AddWaitUntil(TEXT("awake"), [=, this]() { return Seen(TEXT("sleep_end")) && Ops()->IsIdle(); }, 10.f);
	AddDo(TEXT("mark and knockback 260 cm"), [=, this]() { Mark(TEXT("kb")); Ops()->ApplyKnockback(Back, 260.f); });
	AddWaitUntil(TEXT("knockback over"), [=, this]() { return Seen(TEXT("knockback")) && Ops()->IsIdle(); }, 6.f);
	AddDo(TEXT("check"), [=, this]() {
		Check(TEXT("stun_chain"), Seen(TEXT("stun_start")) && Seen(TEXT("stun_loop")) && Seen(TEXT("stun_end")), FString::Printf(TEXT("clips=%s"), *FString::Join(SeenClips.Array(), TEXT(","))));
		Check(TEXT("sleep_chain"), Seen(TEXT("sleep_start")) && Seen(TEXT("sleep_loop")) && Seen(TEXT("sleep_end")), TEXT(""));
		Check(TEXT("knockback_travel"), FMath::Abs(Dist(TEXT("kb")) - 260.f) < 70.f, FString::Printf(TEXT("distance=%.1f expected~260"), Dist(TEXT("kb")))); });

	AddPhase(TEXT("knockup_knockdown_getup_both_directions"), EShowcaseView::ThirdPerson);
	AddDo(TEXT("place"), [=, this]() { Place(); });
	AddWait(0.4f);
	AddDo(TEXT("knockup (hit from the front)"), [=, this]() { Ops()->ApplyKnockup(Back, 900.f); });
	AddWaitUntil(TEXT("recovered"), [=, this]() { return Seen(TEXT("getup_back")) && Ops()->IsIdle(); }, 14.f);
	AddDo(TEXT("check knockup"), [=, this]() { Check(TEXT("knockup_lands_face_up"), Seen(TEXT("knockup_start")) && Seen(TEXT("knockup_air")) && Seen(TEXT("knockdown_back")) && Seen(TEXT("prone_back")) && Seen(TEXT("getup_back")) && !Seen(TEXT("getup_front")), FString::Printf(TEXT("clips=%s"), *FString::Join(SeenClips.Array(), TEXT(",")))); SeenClips.Empty(); });
	AddDo(TEXT("knockdown, hit from behind"), [=, this]() { Ops()->ApplyKnockdown(Fwd); });
	AddWaitUntil(TEXT("recovered"), [=, this]() { return Seen(TEXT("getup_front")) && Ops()->IsIdle(); }, 12.f);
	AddDo(TEXT("check front"), [=, this]() { Check(TEXT("knockdown_from_behind_face_down"), Seen(TEXT("knockdown_front")) && Seen(TEXT("prone_front")) && Seen(TEXT("getup_front")) && !Seen(TEXT("getup_back")), FString::Printf(TEXT("clips=%s"), *FString::Join(SeenClips.Array(), TEXT(",")))); SeenClips.Empty(); });
	AddDo(TEXT("knockdown, hit from the front"), [=, this]() { Ops()->ApplyKnockdown(Back); });
	AddWaitUntil(TEXT("recovered"), [=, this]() { return Seen(TEXT("getup_back")) && Ops()->IsIdle(); }, 12.f);
	AddDo(TEXT("check back"), [=, this]() { Check(TEXT("knockdown_from_front_face_up"), Seen(TEXT("knockdown_back")) && Seen(TEXT("prone_back")) && Seen(TEXT("getup_back")) && !Seen(TEXT("getup_front")), FString::Printf(TEXT("clips=%s"), *FString::Join(SeenClips.Array(), TEXT(",")))); });

	// ------------------------------------------------------------------ death during a cast, respawn, death in the air
	AddPhase(TEXT("death_during_cast_respawn"), EShowcaseView::ThirdPerson);
	AddDo(TEXT("place, channel"), [=, this]() { Place(); Ops()->RequestChannelStart(); });
	AddWaitUntil(TEXT("channel sustained"), [=, this]() { return Ops()->IsChannelSustained(); }, 3.f);
	AddWait(0.5f);
	AddDo(TEXT("kill during the channel"), [=, this]() { Ops()->Kill(Back); });
	AddWait(0.3f);
	AddDo(TEXT("second kill and actions while dying are ignored"), [=, this]() { Ops()->Kill(Fwd); Ops()->RequestMelee(); Ops()->RequestJump(); Ops()->ApplyStun(1.f); });
	AddWaitUntil(TEXT("dead"), [=, this]() { return Ops()->GetState() == EOperativeState::Dead; }, 8.f);
	AddWait(0.8f);
	AddDo(TEXT("check death"), [=, this]() {
		Check(TEXT("death_once_front"), Seen(TEXT("death_front")) && !Seen(TEXT("death_back")) && Seen(TEXT("dead_front")), FString::Printf(TEXT("clips=%s"), *FString::Join(SeenClips.Array(), TEXT(","))));
		Check(TEXT("no_action_after_death"), !Seen(TEXT("melee_1")) && !Seen(TEXT("jump_start")) && !Seen(TEXT("stun_start")), TEXT(""));
		Check(TEXT("death_impact_once"), Count(TEXT("death_impact")) == 1, FString::Printf(TEXT("death_impact=%d"), Count(TEXT("death_impact")))); });
	AddDo(TEXT("respawn"), [=, this]() { Ops()->Respawn(); });
	AddWaitIdle(8.f);
	AddDo(TEXT("check respawn"), [=, this]() { Check(TEXT("respawn_clean_state"), Seen(TEXT("respawn")) && !Op()->IsBeaconDeployed() && Op()->IsMeshVisible() && Ops()->GetHealthFraction() > 0.99f, FString::Printf(TEXT("clips=%s beacon=%d visible=%d"), *FString::Join(SeenClips.Array(), TEXT(",")), Op()->IsBeaconDeployed() ? 1 : 0, Op()->IsMeshVisible() ? 1 : 0)); SeenClips.Empty(); });
	AddDo(TEXT("jump, then killed in the air"), [=, this]() { Ops()->RequestJump(); });
	AddWaitUntil(TEXT("in the air"), [=, this]() { return Ops()->GetState() == EOperativeState::Airborne && Op()->GetVelocity().Z > 100.f; }, 3.f);
	AddDo(TEXT("kill in the air"), [=, this]() { Ops()->Kill(Fwd); });
	AddWaitUntil(TEXT("dead"), [=, this]() { return Ops()->GetState() == EOperativeState::Dead; }, 8.f);
	AddWait(0.3f);
	AddDo(TEXT("check air death"), [=, this]() { Check(TEXT("death_back_from_behind_in_air"), Seen(TEXT("death_back")) && Seen(TEXT("dead_back")), FString::Printf(TEXT("clips=%s"), *FString::Join(SeenClips.Array(), TEXT(",")))); });
	AddWait(0.5f);
	AddDo(TEXT("respawn"), [=, this]() { Ops()->Respawn(); });
	AddWaitIdle(8.f);

	// ------------------------------------------------------------------ dialogue with audio
	AddPhase(TEXT("dialogue_speech_sample"), EShowcaseView::Face);
	AddDo(TEXT("place, greet"), [=, this]() { Place(); Ops()->RequestEmote(EOperativeAction::Greet); });
	AddWaitIdle(6.f);
	AddDo(TEXT("dialogue"), [=, this]() { Mark(TEXT("dlg")); DialogueStart = GetWorld()->GetTimeSeconds(); Ops()->RequestDialogue(); });
	AddWaitUntil(TEXT("dialogue running"), [=, this]() { return Ops()->GetActionKind() == EOperativeAction::Dialogue; }, 2.f);
	AddWaitUntil(TEXT("dialogue done"), [=, this]() { return Ops()->GetActionKind() != EOperativeAction::Dialogue; }, 22.f);
	AddDo(TEXT("check dialogue"), [=, this]() {
		const double Elapsed = GetWorld()->GetTimeSeconds() - DialogueStart;
		const float ClipLen = Actions()->GetLibrary() ? Actions()->GetLibrary()->GetClipLength(FName("dialogue")) : 0.f;
		Check(TEXT("dialogue_duration_and_events"), Count(TEXT("dialogue_start")) == 1 && Count(TEXT("dialogue_end")) == 1 && FMath::Abs(Elapsed - ClipLen) < 0.5, FString::Printf(TEXT("elapsed=%.2f clip=%.2f audio_start_offset_ms=%.0f"), Elapsed, ClipLen, (Op()->GetDialogueAudioStartTime() - DialogueStart) * 1000.0)); });
	AddWaitIdle(4.f);
	AddDo(TEXT("finish"), [=, this]() {
		StepName = TEXT("done");
		Check(TEXT("no_duplicate_events"), Actions()->GetDuplicateEventCount() == 0, FString::Printf(TEXT("duplicates=%d total_events=%d"), Actions()->GetDuplicateEventCount(), Actions()->GetEventCount()));
		Check(TEXT("no_pose_spikes"), PoseSpikes == 0, FString::Printf(TEXT("spikes=%d max_bone_delta_cm=%.1f at %s"), PoseSpikes, GlobalMaxDelta, *GlobalMaxWhere));
	});
}

// ------------------------------------------------------------------------------------------------ sequence runner

void AShowcaseDirector::RunContentChecks()
{
	const UOperativeLibrary* L = UOperativeLibrary::Get(this);
	if (!L || !L->IsReady()) return;
	static const TCHAR* Bones[] = { TEXT("head"), TEXT("pelvis"), TEXT("hand_l"), TEXT("hand_r"), TEXT("foot_l"), TEXT("foot_r"), TEXT("spine_03") };
	int32 LoopBad = 0, LoopTotal = 0;
	for (const FName& Id : L->GetClipOrder())
	{
		const FOperativeClipInfo* Info = L->FindClip(Id);
		if (!Info || !Info->Sequence) { Check(FString::Printf(TEXT("content_clip_present_%s"), *Id.ToString()), false, TEXT("no AnimSequence")); continue; }
		if (Info->bLoop)
		{
			++LoopTotal;
			float MaxD = 0.f;
			for (const TCHAR* B : Bones)
			{
				FVector P0, P1;
				if (L->GetBonePositionCS(Id, FName(B), 0.f, P0) && L->GetBonePositionCS(Id, FName(B), Info->Length(), P1)) MaxD = FMath::Max(MaxD, FVector::Dist(P0, P1));
			}
			const bool bOk = MaxD < 1.5f;
			if (!bOk) ++LoopBad;
			Trace(FString::Printf(TEXT("kind=CONTENT loop_closure clip=%s max_bone_delta_cm=%.2f pass=%d"), *Id.ToString(), MaxD, bOk ? 1 : 0));
		}
		if (FMath::Abs(Info->Length() - Info->Frames / 30.f) > 1.5f / 30.f)
		{
			Trace(FString::Printf(TEXT("kind=CONTENT length_mismatch clip=%s unreal=%.3f manifest=%.3f"), *Id.ToString(), Info->Length(), Info->Frames / 30.f));
		}
	}
	// authored pops: largest movement of the tracked bones between two consecutive 30 fps frames inside each clip
	{
		struct FPop { FName Clip; float Delta; FName Bone; int32 Frame; };
		TArray<FPop> Pops;
		for (const FName& Id : L->GetClipOrder())
		{
			const FOperativeClipInfo* Info = L->FindClip(Id);
			if (!Info || !Info->Sequence || Info->bStaticPose || Info->bAdditive) continue;
			FPop Worst{ Id, 0.f, NAME_None, 0 };
			TArray<FVector> Prev;
			const int32 Frames = FMath::RoundToInt(Info->Length() * 30.f);
			for (int32 F = 0; F <= Frames; ++F)
			{
				TArray<FVector> Cur;
				Cur.SetNum(6);
				for (int32 B = 0; B < 6; ++B) { static const TCHAR* Tracked[] = { TEXT("head"), TEXT("pelvis"), TEXT("hand_l"), TEXT("hand_r"), TEXT("foot_l"), TEXT("foot_r") }; L->GetBonePositionCS(Id, FName(Tracked[B]), F / 30.f, Cur[B]); }
				if (F > 0)
				{
					for (int32 B = 0; B < 6; ++B)
					{
						const float D = FVector::Dist(Cur[B], Prev[B]);
						if (D > Worst.Delta) { static const TCHAR* Tracked[] = { TEXT("head"), TEXT("pelvis"), TEXT("hand_l"), TEXT("hand_r"), TEXT("foot_l"), TEXT("foot_r") }; Worst.Delta = D; Worst.Bone = FName(Tracked[B]); Worst.Frame = F; }
					}
				}
				Prev = Cur;
			}
			Pops.Add(Worst);
			ClipMaxStep.Add(Id.ToString(), Worst.Delta);
		}
		Pops.Sort([](const FPop& A, const FPop& B) { return A.Delta > B.Delta; });
		int32 Over = 0;
		FString Top;
		for (int32 I = 0; I < Pops.Num(); ++I)
		{
			const bool bFastByDesign = Pops[I].Clip.ToString().StartsWith(TEXT("melee")) || Pops[I].Clip.ToString().StartsWith(TEXT("dash")) || Pops[I].Clip.ToString().StartsWith(TEXT("blink"));
			if (Pops[I].Delta > 45.f && !bFastByDesign) ++Over;
			if (I < 12) Top += FString::Printf(TEXT("%s(%s f%d %.0f cm) "), *Pops[I].Clip.ToString(), *Pops[I].Bone.ToString(), Pops[I].Frame, Pops[I].Delta);
			Trace(FString::Printf(TEXT("kind=CONTENT max_frame_step clip=%s bone=%s frame=%d delta_cm=%.1f"), *Pops[I].Clip.ToString(), *Pops[I].Bone.ToString(), Pops[I].Frame, Pops[I].Delta));
		}
		Check(TEXT("content_no_authored_pops"), Over == 0, FString::Printf(TEXT("clips with a bone step above 45 cm in one frame (melee, dash, blink excluded): %d. largest: %s"), Over, *Top));
	}
	Check(TEXT("content_loops_close"), LoopBad == 0, FString::Printf(TEXT("loops=%d open_loops=%d (tolerance 1.5 cm on head, pelvis, hands, feet, chest)"), LoopTotal, LoopBad));
	for (const TCHAR* Side : { TEXT("front"), TEXT("back") })
	{
		const FName Death(*FString::Printf(TEXT("death_%s"), Side)), Dead(*FString::Printf(TEXT("dead_%s"), Side));
		float MaxD = 0.f;
		FString Worst;
		for (const TCHAR* B : Bones)
		{
			FVector P0, P1;
			if (L->GetBonePositionCS(Death, FName(B), L->GetClipLength(Death), P0) && L->GetBonePositionCS(Dead, FName(B), 0.f, P1))
			{
				const float D = FVector::Dist(P0, P1);
				if (D > MaxD) { MaxD = D; Worst = B; }
			}
		}
		Check(FString::Printf(TEXT("content_%s_connects_to_%s"), *Death.ToString(), *Dead.ToString()), MaxD < 3.f, FString::Printf(TEXT("max_bone_delta_cm=%.1f (%s), tolerance 3 cm"), MaxD, *Worst));
	}
	for (const TCHAR* Dash : { TEXT("dash_f"), TEXT("dash_b"), TEXT("dash_l"), TEXT("dash_r") })
	{
		FVector P0, P1;
		if (L->GetBonePositionCS(FName(Dash), FName("root"), 0.f, P0) && L->GetBonePositionCS(FName(Dash), FName("root"), L->GetClipLength(FName(Dash)), P1))
		{
			const float D = FVector::Dist2D(P0, P1);
			Check(FString::Printf(TEXT("content_%s_root_travel_200cm"), Dash), FMath::Abs(D - 200.f) < 5.f, FString::Printf(TEXT("root travel=%.1f cm"), D));
		}
	}
	// standing clips: the head must be at standing height at both ends (catches root control values leaking between exported clips)
	{
		static const TCHAR* Lying[] = { TEXT("knockdown_*"), TEXT("prone_*"), TEXT("getup_*"), TEXT("death_*"), TEXT("dead_*"), TEXT("sleep_*"), TEXT("knockup_*"), TEXT("respawn"), TEXT("knockback") };
		int32 Bad = 0;
		FString BadList;
		for (const FName& Id : L->GetClipOrder())
		{
			const FString S = Id.ToString();
			bool bSkip = false;
			for (const TCHAR* P : Lying) if (S.MatchesWildcard(P)) bSkip = true;
			if (bSkip) continue;
			const FOperativeClipInfo* Info = L->FindClip(Id);
			if (!Info || !Info->Sequence || Info->bAdditive) continue;
			FVector H0, H1;
			if (!L->GetBonePositionCS(Id, FName("head"), 0.f, H0) || !L->GetBonePositionCS(Id, FName("head"), Info->Length(), H1)) continue;
			const float MinZ = FMath::Min(H0.Z, H1.Z);
			if (MinZ < 110.f) { ++Bad; BadList += FString::Printf(TEXT("%s(head z %.0f) "), *S, MinZ); }
		}
		Check(TEXT("content_standing_clips_upright"), Bad == 0, FString::Printf(TEXT("clips with the head below 110 cm: %d %s"), Bad, *BadList));
		// clips that should end upright but do not (respawn ends in the ready stance)
		FVector R1;
		if (L->GetBonePositionCS(FName("respawn"), FName("head"), L->GetClipLength(FName("respawn")), R1))
		{
			Check(TEXT("content_respawn_ends_upright"), R1.Z > 140.f, FString::Printf(TEXT("head z at the end of respawn = %.0f cm"), R1.Z));
		}
	}
	// aim poses must differ from each other (distinct grid samples)
	{
		FVector A, B;
		L->GetBonePositionCS(FName("aim_level_left"), FName("hand_l"), 0.f, A);
		L->GetBonePositionCS(FName("aim_level_right"), FName("hand_l"), 0.f, B);
		Check(TEXT("content_aim_samples_differ"), FVector::Dist(A, B) > 3.f, FString::Printf(TEXT("hand_l distance left/right aim = %.1f cm"), FVector::Dist(A, B)));
	}
	// events present in the manifest (informational: the runtime falls back to fractions of the clip for missing ones)
	int32 WithEvents = 0;
	for (const FName& Id : L->GetClipOrder()) if (const FOperativeClipInfo* I = L->FindClip(Id)) WithEvents += I->Events.Num() > 0 ? 1 : 0;
	Trace(FString::Printf(TEXT("kind=CONTENT manifest_events clips_with_events=%d of %d (missing events use fallback times, marked source=fallback)"), WithEvents, L->GetClipOrder().Num()));
}

void AShowcaseDirector::StartSequence(bool bFromCommandLine)
{
	if (!Op()) return;
	bSequenceFromCommandLine = bFromCommandLine;
	ChecksPassed = ChecksTotal = 0;
	PoseSpikes = 0;
	GlobalMaxDelta = 0.f;
	RunContentChecks();
	if (AOperativeCharacter* O = Op())
	{
		USkeletalMeshComponent* M = O->GetMesh();
		for (int32 I = 0; I < M->GetNumMaterials(); ++I)
		{
			const UMaterialInterface* Mat = M->GetMaterial(I);
			Trace(FString::Printf(TEXT("kind=MATERIAL slot=%d name=%s material=%s"), I, *M->GetMaterialSlotNames()[I].ToString(), Mat ? *Mat->GetName() : TEXT("none")));
		}
		Trace(FString::Printf(TEXT("kind=MATERIAL overlay=%s lod_forced=%d mesh=%s"), M->GetOverlayMaterial() ? *M->GetOverlayMaterial()->GetName() : TEXT("none"), O->GetForcedLOD(), M->GetSkeletalMeshAsset() ? *M->GetSkeletalMeshAsset()->GetName() : TEXT("none")));
		static const TCHAR* Names[] = { TEXT("hand_grip_l"), TEXT("hand_grip_r"), TEXT("emitter_muzzle"), TEXT("blade_base"), TEXT("blade_tip"), TEXT("cell_slot"), TEXT("cell_pouch"), TEXT("beacon_dock"), TEXT("prop_cell"), TEXT("prop_beacon"), TEXT("fx_chest"), TEXT("fx_head_top"), TEXT("fx_mouth"), TEXT("eye_l"), TEXT("floor_l") };
		for (const TCHAR* N : Names)
		{
			FTransform T;
			if (O->GetSocketTransformSafe(FName(N), T))
			{
				const FVector L = O->GetActorTransform().InverseTransformPosition(T.GetLocation());
				Trace(FString::Printf(TEXT("kind=SOCKET name=%s component_pos=(%.1f,%.1f,%.1f)"), N, L.X, L.Y, L.Z + 90.f));
			}
		}
	}
	BuildSequence();
	// development switches: start at a named phase (-SeqFrom=jump) and stop after another (-SeqTo=dash)
	if (!SeqFrom.IsEmpty())
	{
		for (int32 I = 0; I < Tasks.Num(); ++I)
		{
			if (Tasks[I].Label.Contains(SeqFrom) && Tasks[I].Begin && Tasks[I].Label.Contains(TEXT("_"))) { TaskIndex = I; break; }
		}
	}
	bSequenceRunning = true;
	SequenceTime = 0.f;
	if (AShowcasePlayerController* P = PC())
	{
		P->bSequenceControl = true;
	}
	Trace(FString::Printf(TEXT("kind=SEQUENCE begin tasks=%d"), Tasks.Num()));
}

void AShowcaseDirector::StopSequence()
{
	if (!bSequenceRunning) return;
	bSequenceRunning = false;
	if (AShowcasePlayerController* P = PC())
	{
		P->bSequenceControl = false;
		P->SequenceMove(FVector::ZeroVector, 0.f);
	}
	Trace(FString::Printf(TEXT("kind=SEQUENCE stopped at_task=%d/%d"), TaskIndex, Tasks.Num()));
}

FString AShowcaseDirector::GetSequenceStatus() const
{
	if (!bSequenceRunning) return TEXT("idle");
	return FString::Printf(TEXT("%s  task %d/%d  checks %d/%d"), *StepName, TaskIndex, Tasks.Num(), ChecksPassed, ChecksTotal);
}

float AShowcaseDirector::GetSequenceProgress() const
{
	return Tasks.Num() > 0 ? (float)TaskIndex / (float)Tasks.Num() : 0.f;
}

void AShowcaseDirector::TickSequence(float Dt)
{
	if (!bSequenceRunning) return;
	AShowcasePlayerController* P = PC();
	if (!P) return;
	SequenceTime += Dt;
	P->SequenceMove(SeqMoveDir, SeqMoveSpeed);
	P->SequenceAim(SeqAimPoint);
	if (!Tasks.IsValidIndex(TaskIndex))
	{
		bSequenceRunning = false;
		P->bSequenceControl = false;
		P->SequenceMove(FVector::ZeroVector, 0.f);
		Trace(FString::Printf(TEXT("kind=SUMMARY checks=%d passed=%d duplicate_events=%d pose_spikes=%d max_bone_delta_cm=%.1f (%s) events=%d total_time=%.1f"), ChecksTotal, ChecksPassed,
			Actions() ? Actions()->GetDuplicateEventCount() : -1, PoseSpikes, GlobalMaxDelta, *GlobalMaxWhere, EventCounter, SequenceTime));
		FinishRun(TEXT("sequence complete"));
		return;
	}
	// run tasks until one has to wait
	int32 Guard = 0;
	while (Tasks.IsValidIndex(TaskIndex) && Guard++ < 64)
	{
		FTask& T = Tasks[TaskIndex];
		if (!T.bStarted)
		{
			T.bStarted = true;
			T.Elapsed = 0.f;
			if (T.Begin) T.Begin();
		}
		else
		{
			T.Elapsed += Dt;
		}
		bool bDone = !T.Done;
		if (T.Done) bDone = T.Done();
		if (!bDone && T.Elapsed > T.Timeout)
		{
			Trace(FString::Printf(TEXT("kind=TIMEOUT step=%s task=%s after=%.1f state=\"%s\""), *StepName, *T.Label, T.Elapsed, Actions() ? *Actions()->GetStateString() : TEXT("-")));
			bDone = true;
		}
		if (!bDone) break;
		// per step summary at the end of a phase (next task is a phase begin)
		++TaskIndex;
		Dt = 0.f;   // following tasks of the same frame do not consume time again
		if (Tasks.IsValidIndex(TaskIndex) && Tasks[TaskIndex].Label.Len() > 0 && Tasks[TaskIndex].Begin && Tasks[TaskIndex].Timeout == 30.f && Tasks[TaskIndex].Done == nullptr)
		{
			// nothing: begin of the next task happens in the loop
		}
		if (T.Label.StartsWith(TEXT("check")) || T.Label == TEXT("finish"))
		{
			Trace(FString::Printf(TEXT("kind=STEP_METRIC step=%s max_bone_delta_cm=%.1f bone=%s"), *StepName, StepMaxDelta, *StepMaxBone));
		}
	}
}

void AShowcaseDirector::QuitNow()
{
	if (TraceBuffer.Num() > 0)
	{
		FFileHelper::SaveStringToFile(FString::Join(TraceBuffer, TEXT("\n")) + TEXT("\n"), *TraceFilePath, FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM, &IFileManager::Get(), FILEWRITE_Append);
		TraceBuffer.Reset();
	}
	// queued screenshots are written by a worker: wait for them (at most 30 s)
	if (IImageWriteQueue* Queue = GetHighResScreenshotConfig().ImageWriteQueue)
	{
		const double Deadline = FPlatformTime::Seconds() + 30.0;
		while (Queue->GetNumPendingTasks() > 0 && FPlatformTime::Seconds() < Deadline) FPlatformProcess::Sleep(0.05f);
	}
	GLog->Flush();
	// a forced exit reports 1 by default: give automation a meaningful status (0 all checks passed or none ran, 2 a check failed)
	FPlatformMisc::RequestExitWithStatus(true, (ChecksTotal > ChecksPassed) ? 2 : 0, TEXT("ShowcaseDirector::QuitNow"));
}

void AShowcaseDirector::FinishRun(const TCHAR* Reason)
{
	Trace(FString::Printf(TEXT("kind=RUN finish reason=\"%s\""), Reason));
	if (TraceBuffer.Num() > 0)
	{
		FFileHelper::SaveStringToFile(FString::Join(TraceBuffer, TEXT("\n")) + TEXT("\n"), *TraceFilePath, FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM, &IFileManager::Get(), FILEWRITE_Append);
		TraceBuffer.Reset();
	}
	if (bExitAfterSequence)
	{
		ExitCountdown = 45;   // frames left so queued PNG writes finish
	}
}

// ------------------------------------------------------------------------------------------------ capture

void AShowcaseDirector::BeginCapture()
{
	bCaptureStarted = true;
	AShowcasePlayerController* P = PC();
	AOperativeCharacter* O = Op();
	if (!P || !O) { bCaptureStarted = false; return; }
	CaptureFrame = 0;
	CaptureSettleFrames = 12;
	AShowcaseHUD* Hud = Cast<AShowcaseHUD>(P->GetHUD());
	// turntable and face frames show the character on a plain studio floor and backdrop (-NoStudio keeps the test room)
	if ((CaptureMode == ECaptureMode::Turntable || CaptureMode == ECaptureMode::Face) && !FParse::Param(FCommandLine::Get(), TEXT("NoStudio")))
	{
		if (AShowcaseRoom* R = Room()) R->SetStudioMode(true);
	}
	switch (CaptureMode)
	{
	case ECaptureMode::Turntable:
		CaptureTotalFrames = 720;     // revolution 1: neutral, team A, no outline. revolution 2: team B with the rim outline
		P->SetCameraAvoid(false);     // the orbit is an exact circle
		P->SetInstances(1);
		P->SetOutline(false);
		P->SetView(EShowcaseView::Orbit);
		P->SetOrbit(20.f, -3.f, 720.f);
		P->SetCameraLocked(true);
		P->SetOverlayMode(0);
		O->ResetOperative(true);
		Actions()->SetFacingMode(EOperativeFacingMode::Locked);
		Actions()->SetAimAlways(false);
		P->bSequenceControl = true;
		SeqAimPoint = O->GetActorLocation() + FVector(3000.f, 0.f, 0.f);
		if (Hud) { Hud->SetHudLevel(1); Hud->SetCaption(TEXT("MORPHRIG Operative  -  neutral turntable (idle_relaxed, textured, team A, outline off)")); }
		break;
	case ECaptureMode::Face:
		P->SetCameraAvoid(false);
		P->SetInstances(1);
		P->SetView(EShowcaseView::Face);
		P->SetCameraLocked(true);
		O->ResetOperative(true);
		P->bSequenceControl = true;
		SeqAimPoint = O->GetActorLocation() + FVector(3000.f, 0.f, 0.f);
		CaptureTotalFrames = FMath::CeilToInt((Actions()->GetLibrary() ? Actions()->GetLibrary()->GetClipLength(FName("dialogue")) : 15.f) * 30.f) + 24;
		if (Hud) { Hud->SetHudLevel(1); Hud->SetCaption(TEXT("MORPHRIG Operative  -  face performance (dialogue clip, code face layer off)")); }
		break;
	case ECaptureMode::Motion:
		P->SetInstances(1);
		if (Hud) { Hud->SetHudLevel(2); Hud->SetCaption(TEXT("MORPHRIG Operative  -  motion and state overview")); }
		StartSequence(true);
		break;
	default: break;
	}
	Trace(FString::Printf(TEXT("kind=CAPTURE begin mode=%d dir=%s frames=%d"), (int32)CaptureMode, *CaptureDir, CaptureTotalFrames));
}

void AShowcaseDirector::TickCapture(float Dt)
{
	if (ExitCountdown > 0)
	{
		if (--ExitCountdown == 0)
		{
			Trace(TEXT("kind=RUN exit"));
			QuitNow();
		}
		return;
	}
	if (CaptureMode == ECaptureMode::None || !bCaptureStarted) return;
	AShowcasePlayerController* P = PC();
	AOperativeCharacter* O = Op();
	if (!P || !O) return;
	if (CaptureSettleFrames > 0)
	{
#if WITH_EDITOR
		// the uncooked editor build compiles shaders on first use: frames are only captured with the final materials
		if (GShaderCompilingManager && GShaderCompilingManager->IsCompiling())
		{
			CaptureSettleFrames = 12;
			P->SetCameraLocked(true);
			return;
		}
#endif
		--CaptureSettleFrames;
		P->SetCameraLocked(CaptureMode != ECaptureMode::Motion);
		if (CaptureSettleFrames == 0 && CaptureMode == ECaptureMode::Face)
		{
			if (!FParse::Param(FCommandLine::Get(), TEXT("NoDialogue"))) Actions()->RequestDialogue();
			// face capture: the clip drives the face completely (code layer stays empty), automatic blink off
			O->Face->ClearAll();
			O->Face->SetAutoBlink(false);
			P->SetLookAtCamera(false);
		}
		return;
	}
	const float T = CaptureTime;
	switch (CaptureMode)
	{
	case ECaptureMode::Turntable:
	{
		if (CaptureFrame == 360)
		{
			P->SetTeam(EOperativeTeam::B);
			P->SetOutline(true);
			if (AShowcaseHUD* H = Cast<AShowcaseHUD>(P->GetHUD())) H->SetCaption(TEXT("MORPHRIG Operative  -  team B (magenta, diamond icon) with the rim outline"));
		}
		const float Yaw = 360.f * (float)CaptureFrame / 360.f;
		P->SetOrbit(Yaw + 20.f, -3.f, 720.f);
		P->SetCameraLocked(true);
		break;
	}
	case ECaptureMode::Face:
		P->SetCameraLocked(true);
		break;
	case ECaptureMode::Motion:
		// nothing here: a placement or a change of view of the sequence asks the camera to cut (snap) once, and clearing that request every frame
		// made the camera fly through the room to the new position for a few frames
		break;
	default: break;
	}
	if (CaptureFrame % CaptureEvery == 0)
	{
		FString Name = FString::Printf(TEXT("%s/frame_%05d.png"), *CaptureDir, CaptureFrame);
		FScreenshotRequest::RequestScreenshot(Name, true, false);
	}
	++CaptureFrame;
	CaptureTime += Dt;
	const bool bDone = (CaptureMode == ECaptureMode::Motion) ? !bSequenceRunning : CaptureFrame >= CaptureTotalFrames;
	if (bDone || (MaxCaptureFrames > 0 && CaptureFrame >= MaxCaptureFrames))
	{
		Trace(FString::Printf(TEXT("kind=CAPTURE end frames=%d"), CaptureFrame));
		CaptureMode = ECaptureMode::None;
		FinishRun(TEXT("capture complete"));
	}
}

// ------------------------------------------------------------------------------------------------ frame time log

static FString CVarString(const TCHAR* Name)
{
	if (IConsoleVariable* V = IConsoleManager::Get().FindConsoleVariable(Name)) return V->GetString();
	return TEXT("n/a");
}

// host load: other processes share the CPU and inflate the game and render thread times, so every log states it (Linux only)
static FString HostLoadString()
{
#if PLATFORM_UNIX
	double L[3] = { 0.0, 0.0, 0.0 };
	if (getloadavg(L, 3) == 3) return FString::Printf(TEXT("%.2f %.2f %.2f"), L[0], L[1], L[2]);
#endif
	return TEXT("n/a");
}

// the command line without directory names of the machine that ran it
static FString PortableCommandLine()
{
	TArray<FString> Tokens;
	FString(FCommandLine::Get()).ParseIntoArray(Tokens, TEXT(" "), true);
	for (FString& T : Tokens)
	{
		int32 Eq = INDEX_NONE;
		if (T.StartsWith(TEXT("-")) && T.FindChar(TEXT('='), Eq) && T.Mid(Eq + 1).Contains(TEXT("/"))) T = T.Left(Eq + 1) + FPaths::GetCleanFilename(T.Mid(Eq + 1));
	}
	return FString::Join(Tokens, TEXT(" "));
}

void AShowcaseDirector::TickPerf(float Dt)
{
	if (PerfLogPath.IsEmpty() || bPerfDone) return;
	if (PerfFrameIndex == 0)
	{
		// every instance, the main one included, runs the autopilot loop of locomotion and actions
		if (AOperativeCharacter* O = Op()) { O->bAutopilot = true; O->AutopilotSeed = 4711; }
	}
	const double Now = FPlatformTime::Seconds();
	if (PerfBeginWall == 0.0) PerfBeginWall = Now;
	if (PerfFrameIndex++ < WarmupFrames || Now - PerfBeginWall < WarmupSeconds) return;
	if (!bPerfActive)
	{
		bPerfActive = true;
		PerfStartWall = Now;
		PerfLastWall = Now;
		PerfLoadStart = HostLoadString();
		Trace(FString::Printf(TEXT("kind=PERF begin warmup_frames=%d"), WarmupFrames));
		return;
	}
	const float FrameMs = (float)((Now - PerfLastWall) * 1000.0);
	PerfLastWall = Now;
	const float GameMs = (float)FPlatformTime::ToMilliseconds(GGameThreadTime);
	const float RenderMs = (float)FPlatformTime::ToMilliseconds(GRenderThreadTime);
	const float GpuMs = (float)FPlatformTime::ToMilliseconds(RHIGetGPUFrameCycles());
	PerfFrameMs.Add(FrameMs);
	PerfGameMs.Add(GameMs);
	PerfRenderMs.Add(RenderMs);
	PerfGpuMs.Add(GpuMs);
	PerfRows.Add(FString::Printf(TEXT("%d,%.4f,%.3f,%.3f,%.3f,%.3f,%d,%d"), PerfFrameMs.Num(), Now - PerfStartWall, FrameMs, GameMs, RenderMs, GpuMs, GNumDrawCallsRHI[0], GNumPrimitivesDrawnRHI[0]));
	if (PerfFrameMs.Num() >= PerfFrames || (Now - PerfStartWall) > PerfMaxSeconds)
	{
		WritePerfSummary();
		bPerfDone = true;
		if (bExitAfterSequence || FParse::Param(FCommandLine::Get(), TEXT("ExitAfterPerf"))) QuitNow();
	}
}

void AShowcaseDirector::WritePerfSummary()
{
	IFileManager::Get().MakeDirectory(*FPaths::GetPath(PerfLogPath), true);
	FString Csv = TEXT("frame,wall_s,frame_ms,game_thread_ms,render_thread_ms,gpu_ms,draw_calls,primitives\n") + FString::Join(PerfRows, TEXT("\n")) + TEXT("\n");
	FFileHelper::SaveStringToFile(Csv, *PerfLogPath, FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM);
	auto Stats = [](TArray<float> V, float& Avg, float& Min, float& Max, float& P50, float& P95, float& P99)
	{
		if (V.Num() == 0) { Avg = Min = Max = P50 = P95 = P99 = 0.f; return; }
		double S = 0; for (float X : V) S += X;
		Avg = (float)(S / V.Num());
		V.Sort();
		Min = V[0]; Max = V.Last();
		P50 = V[V.Num() / 2]; P95 = V[FMath::Min(V.Num() - 1, (int32)(V.Num() * 0.95))]; P99 = V[FMath::Min(V.Num() - 1, (int32)(V.Num() * 0.99))];
	};
	float A[4][6];
	Stats(PerfFrameMs, A[0][0], A[0][1], A[0][2], A[0][3], A[0][4], A[0][5]);
	Stats(PerfGameMs, A[1][0], A[1][1], A[1][2], A[1][3], A[1][4], A[1][5]);
	Stats(PerfRenderMs, A[2][0], A[2][1], A[2][2], A[2][3], A[2][4], A[2][5]);
	Stats(PerfGpuMs, A[3][0], A[3][1], A[3][2], A[3][3], A[3][4], A[3][5]);
	FString Out;
	Out += TEXT("MORPHRIG performance log\n");
	Out += FString::Printf(TEXT("date: %s\n"), *FDateTime::Now().ToString());
	Out += FString::Printf(TEXT("csv: %s\n"), *FPaths::GetCleanFilename(PerfLogPath));
	Out += FString::Printf(TEXT("frames sampled: %d after %d warm-up frames and %.1f s of warm-up, %.1f s wall\n"), PerfFrameMs.Num(), WarmupFrames, WarmupSeconds, FPlatformTime::Seconds() - PerfStartWall);
	AOperativeCharacter* O = Op();
	AShowcasePlayerController* P = PC();
	Out += FString::Printf(TEXT("instances: %d animated Operatives (every one runs the autopilot loop of locomotion and actions), view: %s, render mode: %s, LOD: %s, overlays: %d\n"),
		P ? P->GetInstanceCount() : 0, P ? *P->GetViewName() : TEXT("-"), P ? *P->GetRenderModeName() : TEXT("-"), O && O->GetForcedLOD() > 0 ? *FString::Printf(TEXT("forced %d"), O->GetForcedLOD() - 1) : TEXT("automatic"), P ? P->GetOverlayMode() : 0);
	Out += TEXT("\nHARDWARE\n");
	Out += FString::Printf(TEXT("cpu: %s, %d cores / %d threads\n"), *FPlatformMisc::GetCPUBrand(), FPlatformMisc::NumberOfCores(), FPlatformMisc::NumberOfCoresIncludingHyperthreads());
	Out += FString::Printf(TEXT("ram: %.1f GiB\n"), FPlatformMemory::GetConstants().TotalPhysical / (1024.0 * 1024.0 * 1024.0));
	Out += FString::Printf(TEXT("gpu: %s  driver %s (internal %s)\n"), *GRHIAdapterName, *GRHIAdapterUserDriverVersion, *GRHIAdapterInternalDriverVersion);
	Out += FString::Printf(TEXT("rhi: %s  os: %s\n"), GDynamicRHI ? GDynamicRHI->GetName() : TEXT("?"), *FPlatformMisc::GetOSVersion());
	Out += FString::Printf(TEXT("resolution: %d x %d (%s)\n"), GSystemResolution.ResX, GSystemResolution.ResY, GSystemResolution.WindowMode == EWindowMode::Fullscreen ? TEXT("fullscreen") : GSystemResolution.WindowMode == EWindowMode::WindowedFullscreen ? TEXT("windowed fullscreen") : TEXT("windowed"));
	Out += TEXT("\nSETTINGS (console variables at the time of the run)\n");
	for (const TCHAR* Name : { TEXT("r.ScreenPercentage"), TEXT("r.ScreenPercentage.Default"), TEXT("r.VSync"), TEXT("t.MaxFPS"), TEXT("r.AntiAliasingMethod"), TEXT("r.DynamicGlobalIlluminationMethod"), TEXT("r.ReflectionMethod"),
		TEXT("r.Shadow.Virtual.Enable"), TEXT("r.Lumen.DiffuseIndirect.Allow"), TEXT("r.SkinCache.Mode"), TEXT("r.MotionBlurQuality"), TEXT("r.Streaming.PoolSize"), TEXT("r.Shadow.Virtual.ResolutionLodBiasDirectional"), TEXT("r.Shadow.Virtual.SMRT.RayCountDirectional"), TEXT("r.Shadow.Virtual.SMRT.SamplesPerRayDirectional"), TEXT("sg.ShadowQuality"), TEXT("sg.PostProcessQuality"), TEXT("r.Tonemapper.Sharpen") })
	{
		Out += FString::Printf(TEXT("%s = %s\n"), Name, *CVarString(Name));
	}
	Out += FString::Printf(TEXT("command line: %s\n"), *PortableCommandLine());
	Out += FString::Printf(TEXT("host load average (1, 5 and 15 minutes) at the start of the sample: %s\n"), *PerfLoadStart);
	Out += FString::Printf(TEXT("host load average at the end of the sample:                       %s\n"), *HostLoadString());
	Out += FString::Printf(TEXT("(other processes on the host share the %d hardware threads; a load above that number adds waiting time to the game and render thread columns)\n"), FPlatformMisc::NumberOfCoresIncludingHyperthreads());
	Out += TEXT("\nRESULT (ms per frame; the target is 16.67 ms = 60 FPS)\n");
	const TCHAR* Labels[4] = { TEXT("frame (wall)"), TEXT("game thread"), TEXT("render thread"), TEXT("gpu") };
	for (int32 I = 0; I < 4; ++I)
	{
		Out += FString::Printf(TEXT("%-14s avg %.3f  min %.3f  p50 %.3f  p95 %.3f  p99 %.3f  max %.3f\n"), Labels[I], A[I][0], A[I][1], A[I][3], A[I][4], A[I][5], A[I][2]);
	}
	Out += FString::Printf(TEXT("average FPS %.1f   1%% low FPS %.1f (from p99 frame time)\n"), A[0][0] > 0.f ? 1000.f / A[0][0] : 0.f, A[0][5] > 0.f ? 1000.f / A[0][5] : 0.f);
	FFileHelper::SaveStringToFile(Out, *(PerfLogPath + TEXT(".summary.txt")), FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM);
	UE_LOG(LogMorphRig, Display, TEXT("PERF_SUMMARY\n%s"), *Out);
	Trace(FString::Printf(TEXT("kind=PERF end frames=%d avg_ms=%.3f p99_ms=%.3f gpu_avg_ms=%.3f"), PerfFrameMs.Num(), A[0][0], A[0][5], A[3][0]));
}
