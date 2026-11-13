#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "ShowcaseDirector.generated.h"

class AOperativeCharacter;
class AShowcaseRoom;
class ACameraActor;

UENUM()
enum class EShowcaseCamera : uint8
{
	TopDown,
	ThirdPerson,
	Front,
	Side,
	Face,
	Orbit,
	Turntable,
	Bust
};

/**
 * Hub of the showcase: owns the Operative instances, camera rig, command interpreter (also used by the UI, the
 * console command `mr`, automation scripts and the deterministic sequence), frame capture, benchmark and trace file.
 */
UCLASS()
class MORPHRIG_API AShowcaseDirector : public AActor
{
	GENERATED_BODY()
public:
	AShowcaseDirector();
	virtual void BeginPlay() override;
	virtual void EndPlay(const EEndPlayReason::Type Reason) override;
	virtual void Tick(float DeltaTime) override;

	static AShowcaseDirector* Get(const UObject* WorldContext);

	/** Executes one command line (see docs/showcase_controls.md). Returns false when the command was unknown or refused. */
	bool Exec(const FString& Line);
	bool RunScriptFile(const FString& Path);
	void RunScriptText(const FString& Text, const FString& Name);
	void StartSequence();
	bool IsScriptRunning() const { return ScriptLines.Num() > 0 && ScriptIndex < ScriptLines.Num(); }
	FString GetScriptStatus() const;

	AOperativeCharacter* GetPrimary() const;
	const TArray<TObjectPtr<AOperativeCharacter>>& GetInstances() const { return Instances; }
	void SetInstanceCount(int32 Count);

	// camera
	EShowcaseCamera CameraMode = EShowcaseCamera::TopDown;
	float OrbitYaw = -135.f, OrbitPitch = -18.f, OrbitDistance = 420.f;
	float TopDownDistance = 1840.f;
	// close-ups follow the head bone: face = chin to hair top with margin, bust = head, shoulders and chest (hand gestures)
	float FaceDistance = 118.f;
	float BustDistance = 225.f;
	// key light: shadow darkness and source angle (soft penumbra); the close-ups use a softer key
	float KeyShadowAmount = 1.0f, KeySourceAngle = 3.0f, CloseShadowAmount = 0.6f, CloseSourceAngle = 7.0f;
	// in the close-ups the key comes from the camera side (three-quarter front): intensity scale, yaw offset to the view, elevation
	float CloseKeyScale = 0.62f, CloseKeyYawOffset = 32.f, CloseKeyPitch = 30.f;
	// front / side / turntable inspection views: same idea at full-body distance
	float InspectKeyScale = 0.85f, InspectKeyYawOffset = 35.f, InspectKeyPitch = 42.f;
	float AppliedKeyYaw = 1.e6f;
	float TurntableYaw = 0.f, TurntableSpeed = 45.f;
	void SetCamera(EShowcaseCamera Mode);
	FString GetCameraName() const;
	FVector GetCameraLocation() const;
	float GetProjectedBodyHeightPx() const { return ProjectedHeightPx; }

	// aim targets
	int32 LockedTarget = INDEX_NONE;
	void LockTarget(int32 Index);

	// HUD switches
	bool bShowHud = true;
	bool bShowSkeleton = false;
	bool bShowHelp = false;
	bool bShowPanel = true;
	bool bScriptedInput = false;        // script drives movement / aim instead of keyboard and mouse
	FVector ScriptMove = FVector::ZeroVector;
	float ScriptMoveTime = 0.f;
	bool bScriptAim = false;
	bool bScriptAimPoint = false;
	FVector ScriptAimPoint = FVector::ZeroVector;
	bool bScriptSprint = false, bScriptWalk = false;
	float ScriptSpeed = -1.f;

	// capture / benchmark state for the HUD
	bool IsCapturing() const { return bCapturing; }
	int32 GetCaptureFrame() const { return CaptureFrame; }
	bool IsBenchmarking() const { return BenchState != 0; }
	FString GetBenchStatus() const;
	const TArray<FString>& GetRecentTrace() const { return RecentTrace; }
	double GetShowcaseTime() const { return ShowTime; }

	void TraceLine(const FString& Line);
	FString Caption;
	float CaptionTime = 0.f;

private:
	void SpawnInstances(int32 Count);
	void UpdateCamera(float Dt);
	void UpdateScript(float Dt);
	void UpdateCapture();
	void UpdateBenchmark(float Dt);
	void FinishBenchmark();
	void OnStateTrace(const AActor* Actor, const FString& Line);
	bool ExecCharacter(AOperativeCharacter* Ch, const TArray<FString>& A);
	bool InjectKey(const FString& KeyName, const FString& Action);
	bool InjectMouse(float X, float Y, const FString& Action);
	void StartCapture(const FString& Dir, float Fps);
	void StopCapture();
	void ApplyPendingTimeStep();

	UPROPERTY(Transient)
	TArray<TObjectPtr<AOperativeCharacter>> Instances;
	UPROPERTY(Transient)
	TObjectPtr<ACameraActor> Camera;
	UPROPERTY(Transient)
	TObjectPtr<AShowcaseRoom> Room;

	int32 Selected = 0;
	double ShowTime = 0.0;
	float ProjectedHeightPx = 0.f;
	FVector CamPos = FVector(-700, -700, 600);
	FRotator CamRot = FRotator(-35, 45, 0);
	float CamFov = 50.f;
	FVector CloseTarget = FVector::ZeroVector;   // damped head position of the close-up cameras
	float CloseYaw = 0.f;
	int32 AppliedKeyLook = -1;
	float InspectYaw = 0.f;             // world yaw of the front / side inspection cameras, captured when they are selected
	bool bCamSnap = true;

	// script
	struct FScriptLine { double At = -1.0; FString Command; };
	TArray<FScriptLine> ScriptLines;
	int32 ScriptIndex = 0;
	double ScriptClock = 0.0;
	double ScriptWaitUntil = 0.0;
	FString ScriptName;
	bool bQuitWhenScriptDone = false;
	bool bScriptWaitIdle = false;
	bool bScriptTimedMove = false;      // a `move x y seconds` issued by the script is still running
	double ScriptWaitIdleUntil = 0.0;
	FString CaptureDirDefault;

	// capture
	bool bCapturing = false;
	bool bCapturePending = false;       // capture requested, waiting for the fixed time step to be applied between frames
	int32 PendingFixedStep = -1;        // -1 nothing, 0 switch to real time, 1 switch to fixed step
	FDelegateHandle BeginFrameHandle;
	// frame capture: the engine hands the read-back frame to OnCaptureFrame, PNG compression runs on the image write queue
	FDelegateHandle ScreenshotHandle;
	FString PendingCaptureFile;
	void OnCaptureFrame(int32 Width, int32 Height, const TArray<FColor>& Bitmap);
	FString CaptureDir;
	int32 CaptureFrame = 0;
	// periodic review screenshots (command autoshot)
	float AutoShotInterval = 0.f;
	float NextAutoShot = 0.f;
	int32 AutoShotIndex = 0;
	FString AutoShotDir;
	float CaptureFps = 30.f;

	// benchmark
	int32 BenchState = 0;       // 0 idle, 1 warm-up, 2 sampling
	float BenchWarmup = 0.f, BenchDuration = 0.f, BenchElapsed = 0.f;
	FString BenchLabel;
	TArray<float> BenchFrameMs, BenchGameMs, BenchRenderMs, BenchGpuMs;
	double BenchLastTime = 0.0;

	// trace
	TArray<FString> RecentTrace;
	FString TraceFile;
	FDelegateHandle TraceHandle;
	TUniquePtr<class FAutoConsoleCommandWithWorldAndArgs> ConsoleCmd;
};
