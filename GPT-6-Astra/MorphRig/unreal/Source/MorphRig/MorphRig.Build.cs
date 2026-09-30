using UnrealBuildTool;
public class MorphRig : ModuleRules {
    public MorphRig(ReadOnlyTargetRules Target) : base(Target) {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        PublicDependencyModuleNames.AddRange(new string[] {"Core","CoreUObject","Engine","InputCore","Slate","SlateCore","ApplicationCore","Json","JsonUtilities","AnimGraphRuntime","AnimationCore","RenderCore","RHI"});
    }
}
